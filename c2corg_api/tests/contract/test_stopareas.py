import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT
from c2corg_api.tests.search.__init__ import reset_search_index

STOPAREAS = ('GET', '/stopareas')
STOPAREA = ('GET', '/stopareas/{id}')
STOPAREA_INFO = ('GET', '/stopareas/{id}/{lang}/info')
WAYPOINT_STOPAREAS = ('GET', '/waypoints/{waypoint_id}/stopareas')
IS_REACHABLE = ('GET', '/waypoints/{waypoint_id}/isReachable')
WAYPOINT_STOPAREA_INFO = ('GET', '/waypoints_stopareas/{id}/{lang}/info')
REACHABLE_ROUTES = ('GET', '/reachableroutes')
REACHABLE_WAYPOINTS = ('GET', '/reachablewaypoints')


@pytest.mark.usefixtures('stoparea_link')
class TestStopareas:
    @contract(STOPAREAS)
    def test_listing(self, browser):
        check_snapshot('stopareas_listing', browser.get('/stopareas'))

    @contract(STOPAREA)
    def test_get(self, browser, stoparea_link):
        check_snapshot(
            'stopareas_get',
            browser.get(f'/stopareas/{stoparea_link.stoparea_id}'),
        )

    @contract(STOPAREA)
    def test_get_unknown(self, browser):
        # a 404 in the error envelope, as the other routes
        response = browser.get('/stopareas/9999999', status=404)
        check_snapshot('stopareas_get_unknown', response)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'Not Found',
                'description': 'Stoparea not found',
            }
        ]

    @contract(STOPAREA_INFO)
    def test_info(self, browser, stoparea_link):
        response = browser.get(f'/stopareas/{stoparea_link.stoparea_id}/en/info')
        check_snapshot('stopareas_info', response)

    @contract(STOPAREA_INFO)
    def test_info_unknown(self, browser):
        response = browser.get('/stopareas/9999999/en/info', status=404)
        check_snapshot('stopareas_info_unknown', response)


@pytest.mark.usefixtures('stoparea_link')
class TestWaypointStopareas:
    @contract(WAYPOINT_STOPAREAS)
    def test_stopareas_of_a_waypoint(self, browser, documents):
        response = browser.get(f'/waypoints/{documents.ids["waypoints"]}/stopareas')
        check_snapshot('waypoint_stopareas', response)
        assert response.json['stopareas'][0]['distance'] == 123.46

    @contract(WAYPOINT_STOPAREAS)
    def test_invalid_waypoint_id(self, browser):
        # as the other ids: a path with an id that is not a number is not found
        response = browser.get('/waypoints/abc/stopareas', status=404)
        check_snapshot('waypoint_stopareas_invalid', response)

    @contract(IS_REACHABLE)
    def test_is_reachable(self, browser, documents):
        response = browser.get(f'/waypoints/{documents.ids["waypoints"]}/isReachable')
        check_snapshot('waypoint_is_reachable', response)
        assert response.json is True

    @contract(IS_REACHABLE)
    def test_is_not_reachable(self, browser):
        response = browser.get('/waypoints/9999999/isReachable')
        assert response.json is False

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info(self, browser, stoparea_link):
        response = browser.get(f'/waypoints_stopareas/{stoparea_link.link_id}/en/info')
        check_snapshot('waypoints_stopareas_info', response)

    @contract(WAYPOINT_STOPAREA_INFO)
    def test_info_unknown(self, browser):
        response = browser.get('/waypoints_stopareas/9999999/en/info', status=404)
        check_snapshot('waypoints_stopareas_info_unknown', response)


@pytest.fixture
def access_id(browser, session, documents, stoparea_link):
    """Add an access waypoint with a stop area to the route; return its id."""
    # only the access waypoints with a stop area make a route reachable
    access_id = browser.create(
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
            child_document_id=documents.ids['routes'],
            child_document_type=ROUTE_TYPE,
        )
    )
    session.add(
        WaypointStoparea(
            waypoint_id=access_id,
            stoparea_id=stoparea_link.stoparea_id,
            distance=50,
        )
    )
    session.flush()
    return access_id


@pytest.mark.usefixtures('access_id')
class TestReachable:
    @contract(REACHABLE_ROUTES, REACHABLE_WAYPOINTS)
    def test_reachable_documents(self, session, browser, documents, access_id):
        # the listings filter with ElasticSearch: one index for both
        reset_search_index(session)
        routes = browser.get('/reachableroutes', params={'pl': 'en'})
        check_snapshot('reachable_routes', routes)
        assert documents.ids['routes'] in [
            d['document_id'] for d in routes.json['documents']
        ]
        waypoints = browser.get('/reachablewaypoints', params={'pl': 'en'})
        check_snapshot('reachable_waypoints', waypoints)
        ids = [d['document_id'] for d in waypoints.json['documents']]
        assert access_id in ids

    @contract(REACHABLE_ROUTES, REACHABLE_WAYPOINTS)
    def test_invalid_parameters(self, browser):
        for path in ('/reachableroutes', '/reachablewaypoints'):
            response = browser.get(path, params={'limit': 'x', 'pl': 'xx'}, status=422)
            check_snapshot('reachable_invalid', response)
            assert [name for _, name, _ in invalid_parameters(response)] == [
                'limit',
                'pl',
            ]
