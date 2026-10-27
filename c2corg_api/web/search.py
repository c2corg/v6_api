"""The simple search: documents of all types matching a word."""

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.search import SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX, search
from c2corg_api.views.area import area_documents_config
from c2corg_api.views.article import article_documents_config
from c2corg_api.views.book import book_documents_config
from c2corg_api.views.image import image_documents_config
from c2corg_api.views.outing import outing_documents_config
from c2corg_api.views.route import route_documents_config
from c2corg_api.views.topo_map import topo_map_documents_config
from c2corg_api.views.user_profile import user_profile_documents_config
from c2corg_api.views.validation import (
    validate_pagination,
    validate_preferred_lang_param,
)
from c2corg_api.views.waypoint import waypoint_documents_config
from c2corg_api.views.xreport import xreport_documents_config
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import validate_query
from c2corg_api.web.db import request_session

# the result keys and the document types, in the order of the answer
SEARCH_TYPES = [
    ('waypoints', WAYPOINT_TYPE, waypoint_documents_config),
    ('xreports', XREPORT_TYPE, xreport_documents_config),
    ('routes', ROUTE_TYPE, route_documents_config),
    ('outings', OUTING_TYPE, outing_documents_config),
    ('areas', AREA_TYPE, area_documents_config),
    ('articles', ARTICLE_TYPE, article_documents_config),
    ('books', BOOK_TYPE, book_documents_config),
    ('maps', MAP_TYPE, topo_map_documents_config),
    ('images', IMAGE_TYPE, image_documents_config),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    app.add_api_route('/search', search_documents, methods=['GET', 'HEAD'])


def search_documents(
    request: Request, user: Annotated[CurrentUser | None, Depends(current_user)]
):
    """Search for a word in the documents of all (or some) types."""
    # GET /search?q=...[&pl=...][&limit=...][&t=...]
    # - q: the word;
    # - pl: matches in this language are ranked first (the documents in other
    #   languages are still returned);
    # - limit: the results per document type (default 10, at most 50);
    # - t: the document types to search, e.g. t=w,r (default: all; the user
    #   profiles only for an authenticated user).
    adapted, error = validate_query(
        request, validate_pagination, validate_preferred_lang_param
    )
    if error is not None:
        return error
    validated = adapted.validated
    limit = validated.get('limit')
    limit = min(SEARCH_LIMIT_DEFAULT if limit is None else limit, SEARCH_LIMIT_MAX)
    types_in = request.query_params.get('t')
    types_to_include = types_in.split(',') if types_in else None

    def included(doc_type):
        return not types_to_include or doc_type in types_to_include

    search_types = [
        (key, config) for key, doc_type, config in SEARCH_TYPES if included(doc_type)
    ]
    if included(USERPROFILE_TYPE) and user is not None:
        search_types.append(('users', user_profile_documents_config))

    with request_session():
        return search.search_for_types(
            search_types,
            request.query_params.get('q'),
            limit,
            validated.get('lang'),
        )
