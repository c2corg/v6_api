from unittest.mock import patch

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.route import get_routes_reachable_ids
from c2corg_api.views.waypoint import build_reachable_waypoints_query

POINT = 'SRID=3857;POINT(635961 5723624)'


class TestReachable(BaseTestRest):
    """Routes whose access waypoint has a stop area, all in an area."""

    def setUp(self):
        super().setUp()
        self.area = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='A')]
        )
        self.session.add(self.area)
        self.session.flush()
        self.access = self.waypoint('access', 'Arret')
        self.summit = self.waypoint('summit', 'Sommet')
        stoparea = Stoparea(
            navitia_id='stop_area:1',
            stoparea_name='Arret',
            line='1',
            operator='Bus',
            geom=POINT,
        )
        self.session.add(stoparea)
        self.session.flush()
        # the stop areas make the access waypoint and the summit reachable,
        # but only an access waypoint makes its routes reachable
        for waypoint in (self.access, self.summit):
            self.session.add(
                WaypointStoparea(
                    waypoint_id=waypoint.document_id,
                    stoparea_id=stoparea.stoparea_id,
                    distance=10,
                )
            )

        self.hiking1 = self.route('hiking', 'Boucle 1', self.access)
        self.hiking2 = self.route('hiking', 'Boucle 2', self.access)
        # the association in the other direction: the route is the parent
        self.skitouring = self.route('skitouring', 'Ski', self.access, reverse=True)
        # linked to the summit only: not reachable
        self.not_reachable = self.route('hiking', 'Sommet', self.summit)
        self.session.flush()
        reset_search_index(self.session)

    def waypoint(self, waypoint_type, title):
        waypoint = Waypoint(
            waypoint_type=waypoint_type,
            elevation=900,
            geometry=DocumentGeometry(geom=POINT),
            locales=[DocumentLocale(lang='fr', title=title)],
        )
        self.session.add(waypoint)
        self.session.flush()
        self.in_area(waypoint)
        return waypoint

    def route(self, activity, title, waypoint, reverse=False):
        route = Route(
            activities=[activity],
            geometry=DocumentGeometry(geom=POINT),
            locales=[RouteLocale(lang='fr', title=title)],
        )
        self.session.add(route)
        self.session.flush()
        parent, child = (route, waypoint) if reverse else (waypoint, route)
        self.session.add(
            Association(
                parent_document_id=parent.document_id,
                parent_document_type=ROUTE_TYPE if reverse else WAYPOINT_TYPE,
                child_document_id=child.document_id,
                child_document_type=WAYPOINT_TYPE if reverse else ROUTE_TYPE,
            )
        )
        self.in_area(route)
        return route

    def in_area(self, document):
        self.session.add(
            AreaAssociation(
                document_id=document.document_id, area_id=self.area.document_id
            )
        )

    def get_ids(self, path, **params):
        body = self.app.get(path, params=params, status=200).json
        for document in body['documents']:
            assert [a['document_id'] for a in document['areas']] == [
                self.area.document_id
            ]
        return [d['document_id'] for d in body['documents']], body['total']

    def test_reachable_route_ids(self):
        # both directions of the associations, access waypoints only
        assert get_routes_reachable_ids() == {
            self.hiking1.document_id,
            self.hiking2.document_id,
            self.skitouring.document_id,
        }

    def test_reachable_routes_paged(self):
        # sorted by id, newest first, as the other listings
        reachable = [
            self.skitouring.document_id,
            self.hiking2.document_id,
            self.hiking1.document_id,
        ]
        assert self.get_ids('/reachableroutes', limit=2) == (reachable[:2], 3)
        assert self.get_ids('/reachableroutes', limit=2, offset=2) == (reachable[2:], 3)
        assert self.get_ids('/reachableroutes', limit=2, offset=3) == ([], 3)

    def test_reachable_routes_filtered(self):
        ids, total = self.get_ids('/reachableroutes', act='skitouring')
        assert (ids, total) == ([self.skitouring.document_id], 1)

    def test_reachable_routes_beyond_the_window_of_elasticsearch(self):
        # past the result window, the page comes from all the filtered ids
        expected = self.get_ids('/reachableroutes', limit=2, offset=1)
        with patch('c2corg_api.views.document.ES_MAX_RESULT_WINDOW', 2):
            assert self.get_ids('/reachableroutes', limit=2, offset=1) == expected

    def test_reachable_waypoints_paged(self):
        reachable = [self.summit.document_id, self.access.document_id]
        assert self.get_ids('/reachablewaypoints', limit=1) == (reachable[:1], 2)
        assert self.get_ids('/reachablewaypoints', limit=1, offset=1) == (
            reachable[1:],
            2,
        )

    def test_navitia_waypoints_query_is_not_paged(self):
        # the Navitia jobs need all the reachable waypoints
        query, total = build_reachable_waypoints_query(
            {}, {'offset': 0, 'limit': 1, 'lang': None}
        )
        ids = [waypoint.document_id for waypoint, _ in query.all()]
        assert (sorted(ids), total) == (
            sorted([self.access.document_id, self.summit.document_id]),
            2,
        )
