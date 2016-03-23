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
        """Search for a query word (simple search).

        Request:
            `GET` `/search?q=...[&lang=...][&limit=...][&t=...]`

        Parameters:
            `q=...`
            The search word.

            `lang=...` (optional)
            When set only the given locale will be included (if available).
            Otherwise all locales will be returned.

            `limit=...` (optional)
            How many results should be returned per document type
            (default: 10). The maximum ist 50.

            `t=...` (optional)
            Which document types should be included in the search. If not
            given, all document types are returned. Example: `...&t=w,r`
            searches only for waypoints and routes.
        """
        search_term = self.request.params.get('q')
        lang = self.request.validated.get('lang')
        limit = self.request.validated.get('limit')
        limit = min(
            SEARCH_LIMIT_DEFAULT if limit is None else limit,
            SEARCH_LIMIT_MAX)
        types_to_include = self._parse_types_to_include(
            self.request.params.get('t'))

        results = {}
        if self._include_type(WAYPOINT_TYPE, types_to_include):
            results['waypoints'] = search.search_for_type(
                search_term, WAYPOINT_TYPE, Waypoint, DocumentLocale,
                schema_waypoint, waypoint_adaptor, limit, lang)

        if self._include_type(ROUTE_TYPE, types_to_include):
            results['routes'] = search.search_for_type(
                search_term, ROUTE_TYPE, Route, RouteLocale,
                schema_route, route_adaptor, limit, lang)

        if self._include_type(OUTING_TYPE, types_to_include):
            results['outings'] = search.search_for_type(
                search_term, OUTING_TYPE, Outing, DocumentLocale,
                schema_outing, outing_adaptor, limit, lang)

        if self._include_type(AREA_TYPE, types_to_include):
            results['areas'] = search.search_for_type(
                search_term, AREA_TYPE, Area, DocumentLocale,
                schema_listing_area, None, limit, lang)

        if self._include_type(MAP_TYPE, types_to_include):
            results['maps'] = search.search_for_type(
                search_term, MAP_TYPE, TopoMap, DocumentLocale,
                schema_listing_topo_map, None, limit, lang)

        if self._include_type(IMAGE_TYPE, types_to_include):
            results['images'] = search.search_for_type(
                search_term, IMAGE_TYPE, Image, DocumentLocale,
                schema_listing_image, None, limit, lang)

        if self._include_type(IMAGE_TYPE, types_to_include) and \
                self.request.has_permission('authenticated'):
            results['users'] = search.search_for_type(
                search_term, USERPROFILE_TYPE, UserProfile, DocumentLocale,
                schema_listing_user_profile, None, limit, lang)

        return results

    def _parse_types_to_include(self, types_in):
        if not types_in:
            return None
        return types_in.split(',')

    def _include_type(self, doc_type, types_to_include):
        if not types_to_include:
            return True
        else:
            return doc_type in types_to_include
