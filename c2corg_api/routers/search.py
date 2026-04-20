"""
FastAPI Search router.

Provides ``/v2/search`` — simple text search across document types.

Mirrors ``c2corg_api.views.search``.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.routers.helpers.document_schemas import (
    area_documents_config,
    article_documents_config,
    book_documents_config,
    image_documents_config,
    outing_documents_config,
    route_documents_config,
    topo_map_documents_config,
    user_profile_documents_config,
    waypoint_documents_config,
    xreport_documents_config,
)
from c2corg_api.routers.helpers.validation import Language
from c2corg_api.search import SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX, search
from c2corg_api.security.fastapi_security import get_optional_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['search'])


def _parse_types(types_in: Optional[str]):
    if not types_in:
        return None
    return types_in.split(',')


def _include_type(doc_type, types_to_include):
    if not types_to_include:
        return True
    return doc_type in types_to_include


@router.get('/search')
def get_search(
    q: Optional[str] = Query(None, description='Search term'),
    pl: Optional[Language] = Query(None, description='Preferred language'),
    limit: Optional[int] = Query(
        SEARCH_LIMIT_DEFAULT, le=SEARCH_LIMIT_MAX, description='Max results per type'
    ),
    t: Optional[str] = Query(None, description='Document types filter'),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Search for a query word (simple search)."""
    types_to_include = _parse_types(t)

    search_types = []
    if _include_type(WAYPOINT_TYPE, types_to_include):
        search_types.append(('waypoints', waypoint_documents_config))

    if _include_type(XREPORT_TYPE, types_to_include):
        search_types.append(('xreports', xreport_documents_config))

    if _include_type(ROUTE_TYPE, types_to_include):
        search_types.append(('routes', route_documents_config))

    if _include_type(OUTING_TYPE, types_to_include):
        search_types.append(('outings', outing_documents_config))

    if _include_type(AREA_TYPE, types_to_include):
        search_types.append(('areas', area_documents_config))

    if _include_type(ARTICLE_TYPE, types_to_include):
        search_types.append(('articles', article_documents_config))

    if _include_type(BOOK_TYPE, types_to_include):
        search_types.append(('books', book_documents_config))

    if _include_type(MAP_TYPE, types_to_include):
        search_types.append(('maps', topo_map_documents_config))

    if _include_type(IMAGE_TYPE, types_to_include):
        search_types.append(('images', image_documents_config))

    if _include_type(USERPROFILE_TYPE, types_to_include) and current_user is not None:
        search_types.append(('users', user_profile_documents_config))

    return search.search_for_types(search_types, q, limit, pl)
