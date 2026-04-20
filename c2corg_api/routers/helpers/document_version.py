"""
Shared helper for the ``/{id}/{lang}/{version_id}`` endpoint.

This is the FastAPI equivalent of the legacy
``c2corg_api.views.document_version.DocumentVersionRest._get_version``.

Caching layers (matching Pyramid behaviour):

1. **ETag** — browser-side 304 Not Modified.
2. **dogpile.cache** — server-side Redis cache keyed by
   ``{doc_id}-{lang}-{version}-{CACHE_VERSION}-{version_id}``.
3. **CacheVersion** — DB-maintained version stamp.
"""

import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy import column, literal_column, union
from sqlalchemy.orm import Session, joinedload

from c2corg_api.caching import cache_document_version, get_or_create
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.user import User
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.routers.helpers.etag import etag_cache
from c2corg_api.routers.helpers.markdown import cook as cook_locale_md

log = logging.getLogger(__name__)


def _is_moderator(user: User | None) -> bool:
    return user is not None and bool(user.moderator)


def get_document_version(
    document_id: int,
    lang: str,
    version_id: int,
    *,
    document_type: str,
    archive_model,
    read_schema,
    locale_archive_model=ArchiveDocumentLocale,
    request: Request,
    response: Response,
    db: Session,
    current_user: User | None = None,
):
    """Load, serialize, and return a specific version of a document.

    Mirrors ``DocumentVersionRest._get_version`` with the same
    three-layer caching: ETag → dogpile (Redis) → DB.

    Parameters
    ----------
    document_id
        Primary key of the document.
    lang
        Language of the version.
    version_id
        Primary key of the ``DocumentVersion`` row.
    document_type
        Short document-type code (``'b'``, ``'r'``, …) for cache key.
    archive_model
        SA archive model (``ArchiveBook``, ``ArchiveRoute``, …).
    read_schema
        The Pydantic ``*ReadSchema`` class for this document type.
    locale_archive_model
        SA archive locale model (default ``ArchiveDocumentLocale``).
        For routes pass ``ArchiveRouteLocale``, etc.
    request
        FastAPI ``Request`` — needed for ``If-None-Match`` inspection.
    response
        FastAPI ``Response`` — used to set the ``ETag`` header.
    db
        Active SA session.
    current_user
        Optional authenticated user.  When a moderator is supplied, masked
        versions are still returned with their document payload and a
        separate cache entry is used (matching the Pyramid ``-mod`` suffix).

    Returns
    -------
    dict
        ``{document, version, previous_version_id, next_version_id}``

    Raises
    ------
    HTTPException(304)
        When the client's ETag matches (Not Modified).
    HTTPException(404)
        When the version doesn't exist or there is no cache version.
    """
    # ── 1. Cache key (version-based) ─────────────────────────────
    base_cache_key = get_cache_key(
        document_id, lang, document_type=document_type, db=db
    )

    if not base_cache_key:
        raise HTTPException(
            status_code=404, detail='no version for document {}'.format(document_id)
        )

    # Append the version_id so each document version is cached separately.
    # Moderators get a distinct cache entry so masked documents are visible
    # to them but not to regular users (same logic as Pyramid's -mod suffix).
    is_mod = _is_moderator(current_user)
    cache_key = '{0}-{1}{2}'.format(
        base_cache_key, version_id, '-mod' if is_mod else ''
    )

    # ── 2. ETag check → 304 if client cache is fresh ────────────
    etag_cache(request, response, cache_key)

    # ── 3. dogpile cache (Redis) → DB fallback ───────────────────
    def create_response():
        return _load_version(
            document_id,
            lang,
            version_id,
            archive_model=archive_model,
            read_schema=read_schema,
            locale_archive_model=locale_archive_model,
            db=db,
            is_moderator=is_mod,
        )

    return get_or_create(cache_document_version, cache_key, create_response)


def _load_version(
    document_id,
    lang,
    version_id,
    *,
    archive_model,
    read_schema,
    locale_archive_model,
    db,
    is_moderator: bool = False,
):
    """Load a specific version from the database.

    This is the inner creator function whose result is stored in
    dogpile / Redis.
    """
    version = (
        db.query(DocumentVersion)
        .options(
            joinedload(DocumentVersion.history_metadata)
            .joinedload(HistoryMetaData.user)
            .load_only(User.id, User.name)
        )
        .options(joinedload(DocumentVersion.document_archive.of_type(archive_model)))
        .options(
            joinedload(
                DocumentVersion.document_locales_archive.of_type(locale_archive_model)
            )
        )
        .options(joinedload(DocumentVersion.document_geometry_archive))
        .filter(DocumentVersion.id == version_id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .first()
    )

    if version is None:
        raise HTTPException(status_code=404, detail='invalid version')

    doc_dict = None
    if not version.masked or is_moderator:
        archive_document = version.document_archive
        archive_document.geometry = version.document_geometry_archive
        archive_document.locales = [version.document_locales_archive]

        doc_schema = read_schema.model_validate(archive_document)
        doc_dict = doc_schema.model_dump(exclude_none=True)

        # Add cooked markdown
        if doc_dict.get('locales'):
            doc_dict['cooked'] = cook_locale_md(doc_dict['locales'][0])

    previous_version_id, next_version_id = get_neighbour_version_ids(
        version_id, document_id, lang, db=db
    )

    return {
        'document': doc_dict,
        'version': serialize_version(version),
        'previous_version_id': previous_version_id,
        'next_version_id': next_version_id,
    }


# ── Pure version helpers (merged from document_version_pure.py) ──


def serialize_version(version):
    return {
        'version_id': version.id,
        'user_id': version.history_metadata.user_id,
        'name': version.history_metadata.user.name,
        'comment': version.history_metadata.comment,
        'written_at': version.history_metadata.written_at.isoformat(),
        'masked': version.masked,
    }


def get_neighbour_version_ids(version_id, document_id, lang, db: Session | None = None):
    db = resolve_db(db)
    """
    Get the previous and next version for a version of a document with a
    specific language.
    """
    next_version = (
        db.query(DocumentVersion.id.label('id'), literal_column('1').label('t'))
        .filter(DocumentVersion.id > version_id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .order_by(DocumentVersion.id)
        .limit(1)
        .subquery()
    )

    previous_version = (
        db.query(DocumentVersion.id.label('id'), literal_column('-1').label('t'))
        .filter(DocumentVersion.id < version_id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .order_by(DocumentVersion.id.desc())
        .limit(1)
        .subquery()
    )

    query = db.query(column('id'), column('t')).select_from(
        union(next_version.select(), previous_version.select()).subquery()
    )

    previous_version_id = None
    next_version_id = None
    for version, typ in query:
        if typ == -1:
            previous_version_id = version
        else:
            next_version_id = version

    return previous_version_id, next_version_id
