from cornice.resource import resource, view

from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.views import cors_policy
from c2corg_api.search import search
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE


@resource(path='/search', cors_policy=cors_policy)
class SearchRest(object):
    def __init__(self, request):
        self.request = request

    @view()
    def get(self):
        search_term = self.request.params['q']

        return {
            'waypoints': search.search_for_type(
                search_term, WAYPOINT_TYPE, Waypoint, 10),
            'routes': search.search_for_type(
                search_term, ROUTE_TYPE, Route, 10)
        }
