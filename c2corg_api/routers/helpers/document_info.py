"""
Shared helper for the ``/{id}/{lang}/info`` endpoint across all
document types.

This is the FastAPI equivalent of the legacy
``c2corg_api.views.document_info.DocumentInfoRest._get_document_info``.

Caching layers (matching Pyramid behaviour):

1. **ETag** — browser-side 304 Not Modified.
2. **dogpile.cache** — server-side Redis cache keyed by
   ``{doc_id}-{lang}-{version}-{CACHE_VERSION}``.
3. **CacheVersion** — DB-maintained version stamp that changes when
   the document or any of its associations is updated.
"""

import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session, joinedload, load_only

from c2corg_api.caching import cache_document_info, get_or_create
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document import Document, DocumentLocale, get_available_langs
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.routers.helpers.document_helpers import set_best_locale
from c2corg_api.routers.helpers.etag import etag_cache

log = logging.getLogger(__name__)

# Map SA model classes → short document-type codes used in cache keys.
# Imports are deferred into the dict to avoid circular-import issues at
# module load time; the dict is populated lazily on first call.
_MODEL_TO_DOCTYPE: dict | None = None


def _get_document_type(document_model) -> str:
    """Return the document-type code (``'b'``, ``'r'``, …) for a model."""
    global _MODEL_TO_DOCTYPE
    if _MODEL_TO_DOCTYPE is None:
        from c2corg_api.models.area import AREA_TYPE, Area
        from c2corg_api.models.article import ARTICLE_TYPE, Article
        from c2corg_api.models.book import BOOK_TYPE, Book
        from c2corg_api.models.image import IMAGE_TYPE, Image
        from c2corg_api.models.outing import OUTING_TYPE, Outing
        from c2corg_api.models.route import ROUTE_TYPE, Route
        from c2corg_api.models.topo_map import MAP_TYPE, TopoMap
        from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile
        from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
        from c2corg_api.models.xreport import XREPORT_TYPE, Xreport

        _MODEL_TO_DOCTYPE = {
            Article: ARTICLE_TYPE,
            Area: AREA_TYPE,
            Book: BOOK_TYPE,
            Image: IMAGE_TYPE,
            Outing: OUTING_TYPE,
            Route: ROUTE_TYPE,
            TopoMap: MAP_TYPE,
            UserProfile: USERPROFILE_TYPE,
            Waypoint: WAYPOINT_TYPE,
            Xreport: XREPORT_TYPE,
        }
    return _MODEL_TO_DOCTYPE[document_model]


def get_document_info(
    document_model,
    document_id: int,
    lang: str,
    *,
    request: Request,
    response: Response,
    db: Session,
):
    """Return basic document info (id + best-locale title).

    Mirrors ``DocumentInfoRest._get_document_info`` with the same
    three-layer caching: ETag → dogpile (Redis) → DB.

    Parameters
    ----------
    document_model
        The SA model class (``Book``, ``Route``, ``Waypoint``, …).
    document_id
        Primary key.
    lang
        Preferred locale language code.
    request
        FastAPI ``Request`` — needed for ``If-None-Match`` inspection.
    response
        FastAPI ``Response`` — used to set the ``ETag`` header.
    db
        Active SA session.

    Returns
    -------
    dict
        JSON-serialisable dict with either a redirect payload or
        ``{document_id, locales: [{lang, title, title_prefix}]}``.

    Raises
    ------
    HTTPException(304)
        When the client's ETag matches (Not Modified).
    HTTPException(404)
        When the document doesn't exist or has no cache version.
    """
    # ── 1. Cache key (version-based) ─────────────────────────────
    document_type = _get_document_type(document_model)
    cache_key = get_cache_key(document_id, lang, document_type=document_type, db=db)

    if not cache_key:
        raise HTTPException(
            status_code=404, detail='no version for document {}'.format(document_id)
        )

    # ── 2. ETag check → 304 if client cache is fresh ────────────
    etag_cache(request, response, cache_key)

    # ── 3. dogpile cache (Redis) → DB fallback ───────────────────
    def create_response():
        return _load_document_info(document_model, document_id, lang, db=db)

    return get_or_create(cache_document_info, cache_key, create_response)


def _load_document_info(document_model, document_id, lang, *, db):
    """Load document info from the database.

    This is the inner creator function whose result is stored in
    dogpile / Redis.
    """
    is_route = document_model is Route

    # Build the locale loading strategy.
    # For Route the locale is a joined-table subclass (RouteLocale),
    # so we cannot mix parent/child columns in a single load_only().
    if is_route:
        locale_opt = joinedload(document_model.locales)
    else:
        locale_opt = joinedload(document_model.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title, DocumentLocale.version
        )

    # First try: load with exact lang match
    document = (
        db.query(document_model)
        .options(
            load_only(
                Document.document_id,
                Document.version,
                Document.redirects_to,
                Document.protected,
            )
        )
        .filter(document_model.document_id == document_id)
        .options(locale_opt)
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail='document not found')

    if document.redirects_to:
        return {
            'redirects_to': document.redirects_to,
            'available_langs': get_available_langs(document.redirects_to, db=db),
        }

    # For UserProfile, grab the user name *before* expunging the
    # document from the session (the association proxy needs the
    # related User object which is lazily loaded).
    is_user_profile = document_model is UserProfile
    user_name = getattr(document, 'name', None) if is_user_profile else None

    # Detach from session so locale trimming doesn't persist
    db.expunge(document)

    # Try exact lang match first, otherwise pick the best locale
    matching = [loc for loc in document.locales if loc.lang == lang]
    if matching:
        document.locales = matching
    else:
        set_best_locale([document], lang, db=db)

    if not document.locales:
        raise HTTPException(status_code=404, detail='document not found')

    assert len(document.locales) == 1
    locale = document.locales[0]

    return {
        'document_id': document.document_id,
        'locales': [
            {
                'lang': locale.lang,
                'title': (
                    locale.title if not is_user_profile else (user_name or locale.title)
                ),
                'title_prefix': (
                    getattr(locale, 'title_prefix', None) if is_route else None
                ),
            }
        ],
    }
