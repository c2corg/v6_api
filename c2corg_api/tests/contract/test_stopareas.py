from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import DocumentContractTest

STOPAREAS = ('GET', '/stopareas')
STOPAREA = ('GET', '/stopareas/{id}')
STOPAREA_INFO = ('GET', '/stopareas/{id}/{lang}/info')
WAYPOINT_STOPAREAS = ('GET', '/waypoints/{waypoint_id}/stopareas')
IS_REACHABLE = ('GET', '/waypoints/{waypoint_id}/isReachable')
WAYPOINT_STOPAREA_INFO = ('GET', '/waypoints_stopareas/{id}/{lang}/info')


class StopareaContractTest(DocumentContractTest):
    """A stop area near the waypoint of DocumentContractTest."""

    def setUp(self):
        super().setUp()
        stoparea = Stoparea(
            navitia_id='stop_area:SNCF:87747006',
            stoparea_name='Grenoble',
            line='TER',
            operator='SNCF',
            geom='SRID=3857;POINT(636150 5652000)',
        )
        self.session.add(stoparea)
        self.session.flush()
        link = WaypointStoparea(
            waypoint_id=self.ids['waypoints'],
            stoparea_id=stoparea.stoparea_id,
            distance=123.456,
        )
        self.session.add(link)
        self.session.flush()
        self.stoparea_id = stoparea.stoparea_id
        self.link_id = link.waypoint_stoparea_id


class TestStopareas(StopareaContractTest):
    @contract(STOPAREAS)
    def test_listing(self):
        check_snapshot('stopareas_listing', self.get('/stopareas'))

    @contract(STOPAREA)
    def test_get(self):
        check_snapshot('stopareas_get', self.get(f'/stopareas/{self.stoparea_id}'))

    @contract(STOPAREA)
    def test_get_unknown(self):
        # a 404 with a body of its own, not a Cornice error
        response = self.get('/stopareas/9999999', status=404)
        check_snapshot('stopareas_get_unknown', response)
        assert response.json == {'error': 'Stoparea not found'}

    @contract(STOPAREA_INFO)
    def test_info(self):
        response = self.get(f'/stopareas/{self.stoparea_id}/en/info')
        check_snapshot('stopareas_info', response)

    @contract(STOPAREA_INFO)
    def test_info_unknown(self):
        response = self.get('/stopareas/9999999/en/info', status=404)
        check_snapshot('stopareas_info_unknown', response)


class TestWaypointStopareas(StopareaContractTest):
    @contract(WAYPOINT_STOPAREAS)
    def test_stopareas_of_a_waypoint(self):
        response = self.get(f'/waypoints/{self.ids["waypoints"]}/stopareas')
        check_snapshot('waypoint_stopareas', response)
        assert response.json['stopareas'][0]['distance'] == 123.46

    @contract(WAYPOINT_STOPAREAS)
    def test_invalid_waypoint_id(self):
        # the validator raises HTTPBadRequest: its json_body is lost, the
        # answer is the error of views.http_error_handler
        response = self.get('/waypoints/abc/stopareas', status=400)
        check_snapshot('waypoint_stopareas_invalid', response)
        assert response.json['errors'] == [
            {'location': 'body', 'name': 'Bad Request', 'description': None}
        ]

    @contract(IS_REACHABLE)
    def test_is_reachable(self):
        response = self.get(f'/waypoints/{self.ids["waypoints"]}/isReachable')
        check_snapshot('waypoint_is_reachable', response)
        assert response.json is True

    @contract(IS_REACHABLE)
    def test_is_not_reachable(self):
        response = self.get('/waypoints/9999999/isReachable')
        assert response.json is False

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info(self):
        response = self.get(f'/waypoints_stopareas/{self.link_id}/en/info')
        check_snapshot('waypoints_stopareas_info', response)

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info_unknown(self):
        response = self.get('/waypoints_stopareas/9999999/en/info', status=404)
        check_snapshot('waypoints_stopareas_info_unknown', response)
