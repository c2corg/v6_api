"""
Shared helpers for the ``POST`` (create) and ``PUT`` (update) endpoints.

These extract the pipeline logic that is common across all document types:
validation → persist → archive → areas/maps → associations → feed → ES sync.

This is the FastAPI equivalent of the legacy
``c2corg_api.views.document.DocumentRest._collection_post`` /
``_create_document`` / ``_put`` / ``update_document``.
"""

import logging

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from c2corg_api.models.area_association import update_areas_for_document
from c2corg_api.models.association import create_associations, synchronize_associations
from c2corg_api.models.cache_version import (
    update_cache_version,
    update_cache_version_associations,
)
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
    UpdateType,
)
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.feed import (
    update_feed_document_create,
    update_feed_document_update,
)
from c2corg_api.models.topo_map_association import update_maps_for_document
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.routers.helpers.validation import (
    association_permission_checker,
    association_permission_removal_checker,
    raise_on_errors,
    validate_associations,
    validate_required,
)
from c2corg_api.search.notify_sync import notify_es_syncer

log = logging.getLogger(__name__)

# ── Settings / ES helpers ────────────────────────────────────────────

_settings_cache: dict | None = None

# Anonymous user ID — populated by ``configure_anonymous()`` at startup.
# When set, xreport creation with ``anonymous=True`` substitutes this
# user ID for the real author in version history.
_anonymous_user_id: int | None = None


def configure_anonymous(settings: dict) -> None:
    """Read the ``guidebook.anonymous_user_account`` setting.

    Called once by :func:`c2corg_api.app.create_app` at startup — mirrors
    ``configure_anonymous`` in ``c2corg_api/__init__.py`` (Pyramid side).
    """
    global _anonymous_user_id
    raw = settings.get('guidebook.anonymous_user_account')
    if raw:
        _anonymous_user_id = int(raw)
    else:
        _anonymous_user_id = None


def _load_settings_once() -> dict:
    """Lazily load settings from the ini file."""
    global _settings_cache
    if _settings_cache is None:
        import configparser
        import os

        ini = os.environ.get('C2CORG_INI', 'development.ini')
        try:
            parser = configparser.ConfigParser()
            parser.read(ini)
            # Pyramid's get_appsettings reads from [app:main];
            # replicate that here.
            section = 'app:main'
            if parser.has_section(section):
                _settings_cache = dict(parser.items(section))
            else:
                _settings_cache = {}
        except Exception:
            _settings_cache = {}
    return _settings_cache


def _notify_es(*, quiet: bool = True):
    """Best-effort ES sync notification."""
    from c2corg_api.search import get_queue_config

    try:
        queue_config = get_queue_config(_load_settings_once())
        notify_es_syncer(queue_config)
    except Exception:
        if not quiet:
            raise
        log.debug('ES sync notification skipped (queue not configured)')


# ── CREATE ───────────────────────────────────────────────────────────


def create_document(
    *,
    model_class,
    body_schema,
    document_type: str,
    required_fields: list[str],
    user,
    db: Session,
    locale_class=None,
    before_add=None,
    after_add=None,
    allow_anonymous: bool = False,
):
    """Full create pipeline shared across document types.

    Parameters
    ----------
    model_class
        SA model class (``Book``, ``Route``, …).
    body_schema
        The validated Pydantic ``Create*Schema`` instance.
    document_type
        E.g. ``BOOK_TYPE``, used for association validation.
    required_fields
        List of required field paths (``['locales', 'locales.title', …]``).
    user
        Authenticated ``User`` instance.
    db
        Active SA session.
    locale_class
        SA locale model class (e.g. ``XreportLocale``).
        Defaults to ``DocumentLocale`` when ``None``.
    before_add / after_add
        Optional callbacks ``(document, user_id)`` called before / after
        ``db.add()``.
    allow_anonymous
        When ``True`` and the request body contains ``anonymous=True``
        and a global anonymous user ID has been configured (via
        ``guidebook.anonymous_user_account``), the anonymous user ID
        is recorded in version history instead of the real author.

    Returns
    -------
    dict   ``{'document_id': int}``
    """
    document_in = body_schema.model_dump(exclude_none=False)

    # Resolve effective user_id (anonymous substitution for xreports)
    if (
        allow_anonymous
        and document_in.get('anonymous')
        and _anonymous_user_id is not None
    ):
        effective_user_id = _anonymous_user_id
    else:
        effective_user_id = user.id

    # 1. Required-field validation
    errors = validate_required(document_in, required_fields, updating=False)
    raise_on_errors(errors)

    # 2. Association validation
    associations_in = document_in.get('associations')
    if associations_in:
        validated, assoc_errors = validate_associations(
            associations_in, document_type, db=db
        )
        raise_on_errors(assoc_errors)
        document_in['associations'] = validated

    # 3. Build SA instance
    document = model_class(
        **body_schema.model_dump(
            exclude={'locales', 'associations', 'document_id', 'version', 'geometry'},
            exclude_none=True,
        )
    )
    _locale_cls = locale_class or DocumentLocale
    if body_schema.locales:
        document.locales = [
            _locale_cls(**loc.model_dump(exclude_none=True))
            for loc in body_schema.locales
        ]

    # Geometry (relationship → needs an SA model, not a plain dict)
    if hasattr(body_schema, 'geometry') and body_schema.geometry is not None:
        geo = body_schema.geometry
        # Access WKBElement attributes directly from the Pydantic model.
        # model_dump() would serialize them to GeoJSON strings via the
        # custom GeometryField serializer, which PostGIS can't parse via
        # ST_GeomFromEWKT.
        geo_kwargs = {}
        if hasattr(geo, 'version') and geo.version is not None:
            geo_kwargs['version'] = geo.version
        if hasattr(geo, 'geom') and geo.geom is not None:
            geo_kwargs['geom'] = geo.geom
        if hasattr(geo, 'geom_detail') and geo.geom_detail is not None:
            geo_kwargs['geom_detail'] = geo.geom_detail
        document.geometry = DocumentGeometry(**geo_kwargs)

    if before_add:
        before_add(document, effective_user_id)

    db.add(document)
    db.flush()

    # 4. Archive / version (coverages have no archive model)
    from c2corg_api.models.coverage import COVERAGE_TYPE

    if document_type != COVERAGE_TYPE:
        create_new_version(document, effective_user_id, db=db)

    # 5. Area & map associations
    # Areas should not be placed "within" other areas; maps likewise.
    from c2corg_api.models.area import AREA_TYPE
    from c2corg_api.models.topo_map import MAP_TYPE

    if document_type != AREA_TYPE:
        update_areas_for_document(document, reset=False, db=db)
    if document_type != MAP_TYPE:
        update_maps_for_document(document, reset=False, db=db)

    # 6. Type-specific post-add callback (e.g. area association update)
    if after_add:
        after_add(document, user_id=effective_user_id)

    # 7. Document associations
    if document_in.get('associations'):
        from c2corg_api.models.outing import OUTING_TYPE

        check_association = association_permission_checker(
            user.id, user.moderator, skip_outing_check=document_type == OUTING_TYPE
        )
        added_associations = create_associations(
            document,
            document_in['associations'],
            effective_user_id,
            check_association=check_association,
            db=db,
        )
        update_cache_version_associations(
            added_associations, [], document.document_id, db=db
        )

    # 8. Feed
    update_feed_document_create(document, effective_user_id, db=db)

    # 9. ES sync
    _notify_es()

    return {'document_id': document.document_id}


# ── UPDATE ───────────────────────────────────────────────────────────


def update_document(
    *,
    document_id: int,
    model_class,
    body_schema,
    document_type: str,
    required_fields: list[str],
    type_specific_attributes: list[str],
    user,
    db: Session,
    locale_class=None,
    locale_attributes: list[str] | None = None,
    before_update=None,
    after_update=None,
    after_update_types=None,
):
    """Full update pipeline shared across document types.

    Parameters
    ----------
    document_id
        URL path id.
    model_class
        SA model class.
    body_schema
        The validated Pydantic ``Update*Schema`` instance (with
        ``.document`` and ``.message``).
    document_type
        E.g. ``BOOK_TYPE``.
    required_fields
        Required field paths.
    type_specific_attributes
        List of attribute names specific to this document type
        (e.g. ``book_attributes``).
    user
        Authenticated ``User`` instance.
    db
        Active SA session.
    before_update / after_update
        Optional callbacks ``(document, doc_schema)``.
    after_update_types
        Optional callback ``(document, update_types)`` called after
        change detection (needed when the callback logic depends on
        what changed, e.g. area geometry updates).

    Returns
    -------
    dict   ``{}``
    """
    doc_schema = body_schema.document
    document_dict = doc_schema.model_dump(exclude_none=False)
    message = body_schema.message

    # 1. Required-field validation
    errors = validate_required(document_dict, required_fields, updating=True)
    raise_on_errors(errors)

    # 2. Load current document
    document = (
        db.query(model_class)
        .filter(model_class.document_id == document_id)
        .options(joinedload(model_class.geometry))
        .options(joinedload(model_class.locales))
        .first()
    )
    if not document:
        raise HTTPException(
            status_code=404,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'name': 'Not Found',
                        'description': 'document not found',
                        'location': 'url',
                    }
                ],
            },
        )

    if document.redirects_to:
        raise HTTPException(status_code=400, detail='can not update merged document')

    if document.protected and not user.moderator:
        raise HTTPException(
            status_code=403, detail='No permission to change a protected document'
        )

    # 3. URL id vs body id
    if document_id != doc_schema.document_id:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'name': 'Bad Request',
                        'description': 'id in the url does not match '
                        'document_id in request body',
                        'location': 'body',
                    }
                ],
            },
        )

    # 4. Version conflict checks
    _check_versions(document, doc_schema)

    # 5. Validate associations
    associations_in = document_dict.get('associations')
    validated_associations = None
    if associations_in:
        validated_associations, assoc_errors = validate_associations(
            associations_in, document_type, db=db
        )
        raise_on_errors(assoc_errors)

    # 6. Remember old versions for change detection
    old_versions = document.get_versions()

    if before_update:
        before_update(document, doc_schema)

    # 7. Apply updates
    _apply_updates(
        document,
        doc_schema,
        type_specific_attributes,
        locale_class=locale_class,
        locale_attributes=locale_attributes,
    )

    try:
        db.flush()
    except StaleDataError:
        raise HTTPException(status_code=409, detail='concurrent modification')

    if after_update:
        after_update(document, doc_schema)

    # 8. Detect what changed
    (update_types, changed_langs) = document.get_update_type(old_versions)

    if after_update_types:
        after_update_types(document, update_types)

    if update_types:
        # Coverages have no archive model — skip versioning.
        from c2corg_api.models.coverage import COVERAGE_TYPE

        if document_type != COVERAGE_TYPE:
            update_version(
                document, user.id, message, update_types, changed_langs, db=db
            )

        # Update area / map intersections when geometry changed.
        from c2corg_api.models.area import AREA_TYPE
        from c2corg_api.models.topo_map import MAP_TYPE

        if document_type != AREA_TYPE and UpdateType.GEOM in update_types:
            update_areas_for_document(document, reset=True, db=db)
        if document_type != MAP_TYPE and UpdateType.GEOM in update_types:
            update_maps_for_document(document, reset=True, db=db)

        update_cache_version(document, db=db)

    # 9. Synchronize associations
    if validated_associations:
        check_add = association_permission_checker(user.id, user.moderator)
        check_remove = association_permission_removal_checker(user.id, user.moderator)
        added, removed = synchronize_associations(
            document,
            validated_associations,
            user.id,
            check_association_add=check_add,
            check_association_remove=check_remove,
            db=db,
        )
    else:
        added, removed = [], []

    if update_types or validated_associations:
        update_feed_document_update(document, user.id, update_types, db=db)
        _notify_es()

    if validated_associations and (removed or added):
        update_cache_version_associations(added, removed, db=db)

    return {}


# ── Internal helpers ─────────────────────────────────────────────────


def _check_versions(document, doc_schema):
    """Check document + locale versions; raise 409 on conflict."""
    if document.version != doc_schema.version:
        raise HTTPException(
            status_code=409,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'name': 'Conflict',
                        'description': 'version of document has changed',
                        'location': 'body',
                    }
                ],
            },
        )
    if doc_schema.locales:
        for locale_in in doc_schema.locales:
            locale = document.get_locale(locale_in.lang)
            if locale and locale.version != locale_in.version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        'status': 'error',
                        'errors': [
                            {
                                'name': 'Conflict',
                                'description': f"version of locale '{locale_in.lang}' "
                                f'has changed',
                                'location': 'body',
                            }
                        ],
                    },
                )
    if (
        document.geometry
        and hasattr(doc_schema, 'geometry')
        and doc_schema.geometry is not None
    ):
        if document.geometry.version != doc_schema.geometry.version:
            raise HTTPException(
                status_code=409,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'name': 'Conflict',
                            'description': 'version of geometry has changed',
                            'location': 'body',
                        }
                    ],
                },
            )


def _apply_updates(
    document,
    doc_schema,
    type_specific_attributes,
    locale_class=None,
    locale_attributes=None,
):
    """Apply field-level updates from the Pydantic schema onto the SA model.

    Only touches fields that were explicitly provided in the request body.
    """
    provided = doc_schema.model_fields_set

    # Document-level whitelisted attributes
    for attr in Document._ATTRIBUTES_WHITELISTED:
        if attr in provided:
            setattr(document, attr, getattr(doc_schema, attr))

    # Type-specific attributes
    for attr in type_specific_attributes:
        if attr in provided:
            setattr(document, attr, getattr(doc_schema, attr))

    # Locales
    _locale_cls = locale_class or DocumentLocale
    _locale_attrs = locale_attributes or []
    if doc_schema.locales:
        for locale_schema in doc_schema.locales:
            locale = document.get_locale(locale_schema.lang)
            if locale:
                for attr in DocumentLocale._ATTRIBUTES_UPDATE:
                    if attr in locale_schema.model_fields_set:
                        setattr(locale, attr, getattr(locale_schema, attr))
                for attr in _locale_attrs:
                    if attr in locale_schema.model_fields_set:
                        setattr(locale, attr, getattr(locale_schema, attr))
                locale.document_id = document.document_id
            else:
                document.locales.append(
                    _locale_cls(**locale_schema.model_dump(exclude_none=True))
                )

    # Geometry
    if hasattr(doc_schema, 'geometry') and doc_schema.geometry is not None:
        geo = doc_schema.geometry
        # geo may be a Pydantic model (normal path) or an SA
        # DocumentGeometry (when before_update copies the existing
        # geometry, e.g. route's update_default_geometry).
        if hasattr(geo, 'model_dump'):
            # Pydantic model — extract WKBElement attributes directly
            # (model_dump serialises them to GeoJSON strings).
            geom_data = {}
            for attr in DocumentGeometry._ATTRIBUTES_UPDATE:
                val = getattr(geo, attr, None)
                if val is not None:
                    geom_data[attr] = val
        else:
            # SA DocumentGeometry — read attributes directly.
            geom_data = {
                attr: getattr(geo, attr)
                for attr in DocumentGeometry._ATTRIBUTES_UPDATE
                if getattr(geo, attr, None) is not None
            }
        if document.geometry:
            for attr in DocumentGeometry._ATTRIBUTES_UPDATE:
                if attr in geom_data:
                    setattr(document.geometry, attr, geom_data[attr])
        else:
            document.geometry = DocumentGeometry(**geom_data)


# ── Versioning helpers ───────────────────────────────────────────────


def create_new_version(document, user_id, written_at=None, db: Session | None = None):
    """Create the first archive version for a newly created document."""
    db = resolve_db(db)
    assert user_id
    archive = document.to_archive()
    archive_locales = document.get_archive_locales()
    archive_geometry = document.get_archive_geometry()

    meta_data = HistoryMetaData(
        comment='creation', user_id=user_id, written_at=written_at
    )
    versions = []
    for locale in archive_locales:
        version = DocumentVersion(
            document_id=document.document_id,
            lang=locale.lang,
            document_archive=archive,
            document_locales_archive=locale,
            document_geometry_archive=archive_geometry,
            history_metadata=meta_data,
        )
        versions.append(version)

    db.add(archive)
    db.add_all(archive_locales)
    db.add(meta_data)
    db.add_all(versions)
    db.flush()


def update_version(
    document, user_id, comment, update_types, changed_langs, db: Session | None = None
):
    """Create a new archive version after an update."""
    db = resolve_db(db)
    assert user_id
    assert update_types

    meta_data = HistoryMetaData(comment=comment, user_id=user_id)
    archive = _get_document_archive(document, update_types, db=db)
    geometry_archive = _get_geometry_archive(document, update_types, db=db)

    langs = _get_langs_to_update(document, update_types, changed_langs)
    locale_versions = []
    for lang in langs:
        locale = document.get_locale(lang)
        locale_archive = _get_locale_archive(locale, changed_langs, db=db)

        version = DocumentVersion(
            document_id=document.document_id,
            lang=locale.lang,
            document_archive=archive,
            document_geometry_archive=geometry_archive,
            document_locales_archive=locale_archive,
            history_metadata=meta_data,
        )
        locale_versions.append(version)

    db.add(archive)
    db.add(meta_data)
    db.add_all(locale_versions)
    db.flush()


def _get_document_archive(document, update_types, db: Session | None = None):

    if UpdateType.FIGURES in update_types:
        archive = document.to_archive()
    else:
        archive = (
            db.query(ArchiveDocument)
            .filter(
                ArchiveDocument.version == document.version,
                ArchiveDocument.document_id == document.document_id,
            )
            .one()
        )
    return archive


def _get_geometry_archive(document, update_types, db: Session | None = None):

    if not document.geometry:
        return None
    elif UpdateType.GEOM in update_types:
        archive = document.geometry.to_archive()
    else:
        archive = (
            db.query(ArchiveDocumentGeometry)
            .filter(
                ArchiveDocumentGeometry.version == document.geometry.version,
                ArchiveDocumentGeometry.document_id == document.document_id,
            )
            .one()
        )
    return archive


def _get_langs_to_update(document, update_types, changed_langs):
    if UpdateType.GEOM not in update_types and UpdateType.FIGURES not in update_types:
        return changed_langs
    else:
        return [locale.lang for locale in document.locales]


def _get_locale_archive(locale, changed_langs, db: Session | None = None):

    if locale.lang in changed_langs:
        locale_archive = locale.to_archive()
    else:
        locale_archive = (
            db.query(ArchiveDocumentLocale)
            .filter(
                ArchiveDocumentLocale.version == locale.version,
                ArchiveDocumentLocale.document_id == locale.document_id,
                ArchiveDocumentLocale.lang == locale.lang,
            )
            .one()
        )
    return locale_archive


def revert_update_document(
    document,
    document_in,
    *,
    user_id,
    is_moderator,
    message,
    associations=None,
    queue_config=None,
    before_update=None,
    after_update=None,
    manage_versions=None,
    db: Session | None = None,
):
    """Apply an update to a document (used by the revert endpoint).

    This is the standalone equivalent of
    ``DocumentRest.update_document``.

    Parameters
    ----------
    user_id : int
    is_moderator : bool
    message : str          Version-history comment.
    associations : dict    Validated associations (usually ``None`` for reverts).
    queue_config           ES queue config (``None`` skips ES sync).
    """
    from c2corg_api.models.area import AREA_TYPE
    from c2corg_api.models.area_association import update_areas_for_document
    from c2corg_api.models.cache_version import (
        update_cache_version,
        update_cache_version_associations,
    )
    from c2corg_api.models.coverage import COVERAGE_TYPE
    from c2corg_api.models.topo_map import MAP_TYPE
    from c2corg_api.models.topo_map_association import update_maps_for_document
    from c2corg_api.search.notify_sync import notify_es_syncer

    db = resolve_db(db)
    old_versions = document.get_versions()

    if before_update:
        before_update(document, document_in)

    document.update(document_in)

    if manage_versions:
        manage_versions(document, old_versions)

    try:
        db.flush()
    except StaleDataError:
        raise HTTPException(status_code=409, detail='concurrent modification')

    (update_types, changed_langs) = document.get_update_type(old_versions)

    if update_types:
        if document.type != COVERAGE_TYPE:
            update_version(document, user_id, message, update_types, changed_langs)

        if document.type != AREA_TYPE and UpdateType.GEOM in update_types:
            update_areas_for_document(document, reset=True)

        if document.type != MAP_TYPE and UpdateType.GEOM in update_types:
            update_maps_for_document(document, reset=True)

        if after_update:
            after_update(document, update_types, user_id=user_id)

        update_cache_version(document)

    if associations:
        check_association_add = association_permission_checker(user_id, is_moderator)
        check_association_remove = association_permission_removal_checker(
            user_id, is_moderator
        )

        added_associations, removed_associations = synchronize_associations(
            document,
            associations,
            user_id,
            check_association_add=check_association_add,
            check_association_remove=check_association_remove,
        )

    if update_types or associations:
        if queue_config is not None:
            notify_es_syncer(queue_config)
        update_feed_document_update(document, user_id, update_types)
    if associations and (removed_associations or added_associations):
        update_cache_version_associations(added_associations, removed_associations)

    return update_types


# ── Geometry helpers ─────────────────────────────────────────────────


def set_default_geom_from_associations(doc, linked_docs, update_always=False, db=None):
    """Compute a default centroid geometry from linked waypoints.

    Used by outing creation/update to set a geometry when none is provided.
    """
    db = resolve_db(db)

    if update_always or doc.geometry is None or doc.geometry.geom is None:
        default_geom = _get_default_geom(linked_docs, db=db)

        if default_geom is not None:
            if doc.geometry is not None:
                doc.geometry.geom = default_geom
            else:
                doc.geometry = DocumentGeometry(geom=default_geom)
        else:
            log.warning(
                'Creating or updating document {} without default geometry'.format(
                    doc.document_id
                )
            )


def _get_default_geom(linked_docs, db):

    if not linked_docs:
        return None

    linked_waypoint_ids = [d['document_id'] for d in linked_docs]
    default_geom = (
        db.query(
            func.ST_SetSRID(
                func.ST_Centroid(
                    func.ST_ConvexHull(func.ST_Collect(DocumentGeometry.geom))
                ),
                3857,
            )
        )
        .filter(DocumentGeometry.document_id.in_(linked_waypoint_ids))
        .scalar()
    )

    return default_geom
