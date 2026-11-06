import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT, DocumentContractTest
from c2corg_api.tests.search.__init__ import reset_search_index

STOPAREAS = ('GET', '/stopareas')
STOPAREA = ('GET', '/stopareas/{id}')
STOPAREA_INFO = ('GET', '/stopareas/{id}/{lang}/info')
WAYPOINT_STOPAREAS = ('GET', '/waypoints/{waypoint_id}/stopareas')
IS_REACHABLE = ('GET', '/waypoints/{waypoint_id}/isReachable')
WAYPOINT_STOPAREA_INFO = ('GET', '/waypoints_stopareas/{id}/{lang}/info')
REACHABLE_ROUTES = ('GET', '/reachableroutes')
REACHABLE_WAYPOINTS = ('GET', '/reachablewaypoints')


class StopareaContractTest(DocumentContractTest):
    """A stop area near the waypoint of DocumentContractTest."""

    @pytest.fixture(autouse=True)
    def _setup_stoparea_contract_test(
        self, client, session, _setup_document_contract_test
    ):
        stoparea = Stoparea(
            navitia_id='stop_area:SNCF:87747006',
            stoparea_name='Grenoble',
            line='TER',
            operator='SNCF',
            geom='SRID=3857;POINT(636150 5652000)',
        )
        session.add(stoparea)
        session.flush()
        link = WaypointStoparea(
            waypoint_id=self.ids['waypoints'],
            stoparea_id=stoparea.stoparea_id,
            distance=123.456,
        )
        session.add(link)
        session.flush()
        self.stoparea_id = stoparea.stoparea_id
        self.link_id = link.waypoint_stoparea_id


class TestStopareas(StopareaContractTest):
    @contract(STOPAREAS)
    def test_listing(self, client, settings):
        check_snapshot('stopareas_listing', self.get(client, settings, '/stopareas'))

    @contract(STOPAREA)
    def test_get(self, client, settings):
        check_snapshot(
            'stopareas_get',
            self.get(client, settings, f'/stopareas/{self.stoparea_id}'),
        )

    @contract(STOPAREA)
    def test_get_unknown(self, client, settings):
        # a 404 in the error envelope, as the other routes
        response = self.get(client, settings, '/stopareas/9999999', status=404)
        check_snapshot('stopareas_get_unknown', response)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'Not Found',
                'description': 'Stoparea not found',
            }
        ]

    @contract(STOPAREA_INFO)
    def test_info(self, client, settings):
        response = self.get(client, settings, f'/stopareas/{self.stoparea_id}/en/info')
        check_snapshot('stopareas_info', response)

    @contract(STOPAREA_INFO)
    def test_info_unknown(self, client, settings):
        response = self.get(client, settings, '/stopareas/9999999/en/info', status=404)
        check_snapshot('stopareas_info_unknown', response)


class TestWaypointStopareas(StopareaContractTest):
    @contract(WAYPOINT_STOPAREAS)
    def test_stopareas_of_a_waypoint(self, client, settings):
        response = self.get(
            client, settings, f'/waypoints/{self.ids["waypoints"]}/stopareas'
        )
        check_snapshot('waypoint_stopareas', response)
        assert response.json['stopareas'][0]['distance'] == 123.46

    @contract(WAYPOINT_STOPAREAS)
    def test_invalid_waypoint_id(self, client, settings):
        # as the other ids: a path with an id that is not a number is not found
        response = self.get(client, settings, '/waypoints/abc/stopareas', status=404)
        check_snapshot('waypoint_stopareas_invalid', response)

    @contract(IS_REACHABLE)
    def test_is_reachable(self, client, settings):
        response = self.get(
            client, settings, f'/waypoints/{self.ids["waypoints"]}/isReachable'
        )
        check_snapshot('waypoint_is_reachable', response)
        assert response.json is True

    @contract(IS_REACHABLE)
    def test_is_not_reachable(self, client, settings):
        response = self.get(client, settings, '/waypoints/9999999/isReachable')
        assert response.json is False

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info(self, client, settings):
        response = self.get(
            client, settings, f'/waypoints_stopareas/{self.link_id}/en/info'
        )
        check_snapshot('waypoints_stopareas_info', response)

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info_unknown(self, client, settings):
        response = self.get(
            client, settings, '/waypoints_stopareas/9999999/en/info', status=404
        )
        check_snapshot('waypoints_stopareas_info_unknown', response)


class TestReachable(StopareaContractTest):
    @pytest.fixture(autouse=True)
    def _setup_test_reachable(
        self, client, session, settings, _setup_stoparea_contract_test
    ):
        # only the access waypoints with a stop area make a route reachable
        access_id = self.create(
            client,
            settings,
            'waypoints',
            {
                'waypoint_type': 'access',
                'elevation': 900,
                'geometry': {'geom': POINT},
                'locales': [{'lang': 'en', 'title': 'Bus stop'}],
            },
        )
        session.add(
            Association(
                parent_document_id=access_id,
                parent_document_type=WAYPOINT_TYPE,
                child_document_id=self.ids['routes'],
                child_document_type=ROUTE_TYPE,
            )
        )
        session.add(
            WaypointStoparea(
                waypoint_id=access_id, stoparea_id=self.stoparea_id, distance=50
            )
        )
        session.flush()
        self.access_id = access_id

    @contract(REACHABLE_ROUTES, REACHABLE_WAYPOINTS)
    def test_reachable_documents(self, client, session, settings):
        # the listings filter with ElasticSearch: one index for both
        reset_search_index(session)
        routes = self.get(client, settings, '/reachableroutes', params={'pl': 'en'})
        check_snapshot('reachable_routes', routes)
        assert self.ids['routes'] in [
            d['document_id'] for d in routes.json['documents']
        ]
        waypoints = self.get(
            client, settings, '/reachablewaypoints', params={'pl': 'en'}
        )
        check_snapshot('reachable_waypoints', waypoints)
        ids = [d['document_id'] for d in waypoints.json['documents']]
        assert self.access_id in ids

    @contract(REACHABLE_ROUTES, REACHABLE_WAYPOINTS)
    def test_invalid_parameters(self, client, settings):
        for path in ('/reachableroutes', '/reachablewaypoints'):
            response = self.get(
                client, settings, path, params={'limit': 'x', 'pl': 'xx'}, status=422
            )
            check_snapshot('reachable_invalid', response)
            assert [name for _, name, _ in invalid_parameters(response)] == [
                'limit',
                'pl',
            ]
