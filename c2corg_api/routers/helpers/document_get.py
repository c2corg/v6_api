"""
Shared helper for the ``GET /{id}`` single-document endpoint.

This is the FastAPI equivalent of the legacy
``c2corg_api.views.document.DocumentRest._get`` / ``_get_in_lang``.

Caching layers (matching Pyramid behaviour):

1. **ETag** — browser-side 304 Not Modified.
2. **dogpile.cache** — server-side Redis cache keyed by
   ``{doc_id}-{lang}-{version}-{CACHE_VERSION}``.
   Uses ``cache_document_cooked`` when the ``cook`` parameter is set,
   otherwise ``cache_document_detail``.
3. **CacheVersion** — DB-maintained version stamp.

Note: editing view (``?e=1``) bypasses all caching, same as Pyramid.
"""

import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session, joinedload

import c2corg_api.routers.helpers.document_associations as doc_associations
from c2corg_api.caching import (
    cache_document_cooked,
    cache_document_detail,
    get_or_create,
)
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import get_available_langs, set_available_langs
from c2corg_api.routers.helpers.document_helpers import set_best_locale
from c2corg_api.routers.helpers.etag import etag_cache
from c2corg_api.routers.helpers.markdown import cook as cook_locale_md

log = logging.getLogger(__name__)


def get_single_document(
    document_model,
    document_id: int,
    *,
    document_type: str,
    lang: str | None = None,
    editing_view: bool = False,
    cook: str | None = None,
    read_schema,
    include_areas: bool = True,
    include_maps: bool = False,
    set_custom_associations=None,
    set_custom_fields=None,
    extra_query_options=None,
    request: Request,
    response: Response,
    db: Session,
):
    """Load a single document, apply locale selection, associations, and
    serialize via the given Pydantic *read_schema*.

    Mirrors ``DocumentRest._get`` with the same caching layers:
    ETag → dogpile (Redis) → DB.  Editing view bypasses all caching.

    Parameters
    ----------
    document_model
        SA model class (``Book``, ``Route``, ``Waypoint``, …).
    document_id
        Primary key.
    document_type
        Short document-type code (``'b'``, ``'r'``, …) for cache key.
    lang
        Requested locale language (``?l=``).  Mutually exclusive with *cook*.
    editing_view
        Whether the request is for the editing view (``?e=1``).
    cook
        If set, a single "best" locale is selected and ``result.cooked``
        is populated with the cooked markdown.
    read_schema
        The Pydantic read-schema class for this document type.
    include_areas
        Whether to attach area info (default ``True``).
        Books disable this.
    include_maps
        Whether to attach topo-map info (default ``False``).
        Waypoints and routes enable this.
    set_custom_associations
        Optional callback ``(document, lang)`` to set extra associations
        (e.g. recent outings for routes/waypoints).
    set_custom_fields
        Optional callback ``(document)`` to set extra fields
        (e.g. author on articles).
    extra_query_options
        Optional list of SA query options (e.g.
        ``[joinedload(UserProfile.user)]``) appended to the base
        query.  Useful when association proxies or other relationships
        must survive ``db.expunge()``.
    request
        FastAPI ``Request`` — needed for ``If-None-Match`` inspection.
    response
        FastAPI ``Response`` — used to set the ``ETag`` header.
    db
        Active SA session.

    Returns
    -------
    Pydantic model instance (``read_schema``)

    Raises
    ------
    HTTPException
    """
    if cook and lang:
        raise HTTPException(
            status_code=400,
            detail="You can't use cook service with explicit lang query",
        )
    if cook and editing_view:
        raise HTTPException(
            status_code=400, detail="You can't use cook service with edition mode"
        )
    if cook:
        lang = cook

    cache = cache_document_cooked if cook else cache_document_detail

    def create_response():
        return _load_single_document(
            document_model,
            document_id,
            lang=lang,
            editing_view=editing_view,
            cook=cook,
            read_schema=read_schema,
            include_areas=include_areas,
            include_maps=include_maps,
            set_custom_associations=set_custom_associations,
            set_custom_fields=set_custom_fields,
            extra_query_options=extra_query_options,
            db=db,
        )

    if not editing_view:
        cache_key = get_cache_key(document_id, lang, document_type=document_type, db=db)
        if cache_key:
            # ETag check → 304 if client cache is fresh
            etag_cache(request, response, cache_key)
            # dogpile cache (Redis) → DB fallback
            return get_or_create(cache, cache_key, create_response)

    # don't cache if requesting a document for editing
    return create_response()


def _load_single_document(
    document_model,
    document_id,
    *,
    lang,
    editing_view,
    cook,
    read_schema,
    include_areas,
    include_maps=False,
    set_custom_associations,
    set_custom_fields=None,
    extra_query_options=None,
    db,
):
    """Load a single document from the database.

    This is the inner creator function whose result is stored in
    dogpile / Redis.
    """
    document = (
        db.query(document_model)
        .filter(document_model.document_id == document_id)
        .options(joinedload(document_model.geometry))
        .options(joinedload(document_model.locales))
    )
    if extra_query_options:
        for opt in extra_query_options:
            document = document.options(opt)
    document = document.first()

    if not document:
        raise HTTPException(status_code=404, detail='document not found')

    if document.redirects_to:
        return {
            'document_id': document.document_id,
            'redirects_to': document.redirects_to,
            'available_langs': get_available_langs(document.redirects_to, db=db),
        }

    # Locale selection
    if lang and not cook:
        db.expunge(document)
        matching = [loc for loc in document.locales if loc.lang == lang]
        document.locales = matching if matching else []
    elif cook:
        set_best_locale([document], cook, db=db)

    set_available_langs([document], db=db)

    # Associations
    document.associations = doc_associations.get_associations(
        document, lang, editing_view, db=db
    )

    if not editing_view and set_custom_associations:
        set_custom_associations(document, lang)

    if set_custom_fields:
        set_custom_fields(document)

    # Area associations (waypoints, routes, outings, xreports, …)
    if not editing_view and include_areas:
        from c2corg_api.models.area_association import get_areas as _get_areas
        from c2corg_api.schemas.listing import AreaListingSchema

        doc_areas = _get_areas(document, lang, db=db)
        document.areas = [
            AreaListingSchema.model_validate(m).model_dump(exclude_none=True)
            for m in doc_areas
        ]

    # Topo-map associations (waypoints, routes, …)
    if include_maps:
        from c2corg_api.models.topo_map_association import get_maps as _get_maps
        from c2corg_api.schemas.listing import TopoMapListingSchema

        topo_maps = _get_maps(document, lang, db=db)
        document.maps = [
            TopoMapListingSchema.model_validate(m).model_dump(exclude_none=True)
            for m in topo_maps
        ]

    # Serialize
    result = read_schema.model_validate(document)

    if cook:
        locale_dict = result.locales[0].model_dump() if result.locales else {}
        result.cooked = cook_locale_md(locale_dict)

    # Build exclusion set for fields that should be absent from the JSON
    # (matching Pyramid/colander behaviour where these keys were simply
    # not part of the serialization schema).
    exclude = set()
    if not include_maps:
        exclude.add('maps')
    if not include_areas or editing_view:
        exclude.add('areas')
    if not cook:
        exclude.add('cooked')
    if not getattr(document, 'redirects_to', None):
        exclude.add('redirects_to')

    return result.model_dump(exclude=exclude or None)
