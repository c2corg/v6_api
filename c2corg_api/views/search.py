from cornice.resource import resource, view

from c2corg_api.views.validation import validate_pagination
from c2corg_api.models.route import Route, ROUTE_TYPE, schema_route
from c2corg_api.views import cors_policy
from c2corg_api.search import search
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE, schema_waypoint
from c2corg_api.views.route import listing_schema_adaptor \
    as route_adaptor
from c2corg_api.views.waypoint import listing_schema_adaptor \
    as waypoint_adaptor

# the maximum number of documents that can be returned for each document type
SEARCH_LIMIT_MAX = 50

# the default limit value (how much documents are returned at once for each
# document type in a search request)
SEARCH_LIMIT_DEFAULT = 10


@resource(path='/search', cors_policy=cors_policy)
class SearchRest(object):
    def __init__(self, request):
        self.request = request

    @view(validators=validate_pagination)
    def get(self):
        search_term = self.request.params.get('q')
        limit = self.request.validated.get('limit')
        limit = min(
            SEARCH_LIMIT_DEFAULT if limit is None else limit,
            SEARCH_LIMIT_MAX)

        return {
            'waypoints': search.search_for_type(
                search_term, WAYPOINT_TYPE, Waypoint, schema_waypoint,
                waypoint_adaptor, limit),
            'routes': search.search_for_type(
                search_term, ROUTE_TYPE, Route, schema_route,
                route_adaptor, limit)
        }
