from c2corg_api.models.area import AREA_TYPE, Area, \
    schema_listing_area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.image import IMAGE_TYPE, Image, schema_listing_image
from c2corg_api.models.outing import OUTING_TYPE, Outing, schema_outing
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap, \
    schema_listing_topo_map
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile, \
    schema_listing_user_profile
from cornice.resource import resource, view

from c2corg_api.views.validation import validate_pagination, \
    validate_preferred_lang_param
from c2corg_api.models.route import Route, ROUTE_TYPE, schema_route, \
    RouteLocale
from c2corg_api.views import cors_policy
from c2corg_api.search import search
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE, schema_waypoint
from c2corg_api.views.route import listing_schema_adaptor \
    as route_adaptor
from c2corg_api.views.waypoint import listing_schema_adaptor \
    as waypoint_adaptor
from c2corg_api.views.outing import listing_schema_adaptor \
    as outing_adaptor

# the maximum number of documents that can be returned for each document type
SEARCH_LIMIT_MAX = 50

# the default limit value (how many documents are returned at once for each
# document type in a search request)
SEARCH_LIMIT_DEFAULT = 10


@resource(path='/search', cors_policy=cors_policy)
class SearchRest(object):
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def get(self):
        search_term = self.request.params.get('q')
        lang = self.request.validated.get('lang')
        limit = self.request.validated.get('limit')
        limit = min(
            SEARCH_LIMIT_DEFAULT if limit is None else limit,
            SEARCH_LIMIT_MAX)

        return {
            'waypoints': search.search_for_type(
                search_term, WAYPOINT_TYPE, Waypoint, DocumentLocale,
                schema_waypoint, waypoint_adaptor, limit, lang),
            'routes': search.search_for_type(
                search_term, ROUTE_TYPE, Route, RouteLocale,
                schema_route, route_adaptor, limit, lang),
            'outings': search.search_for_type(
                search_term, OUTING_TYPE, Outing, DocumentLocale,
                schema_outing, outing_adaptor, limit, lang),
            'areas': search.search_for_type(
                search_term, AREA_TYPE, Area, DocumentLocale,
                schema_listing_area, None, limit, lang),
            'maps': search.search_for_type(
                search_term, MAP_TYPE, TopoMap, DocumentLocale,
                schema_listing_topo_map, None, limit, lang),
            'images': search.search_for_type(
                search_term, IMAGE_TYPE, Image, DocumentLocale,
                schema_listing_image, None, limit, lang),
            'users': search.search_for_type(
                search_term, USERPROFILE_TYPE, UserProfile, DocumentLocale,
                schema_listing_user_profile, None, limit, lang)
            if self.request.has_permission('authenticated') else {}
        }
