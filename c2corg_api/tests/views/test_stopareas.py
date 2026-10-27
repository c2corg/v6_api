from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.views import BaseDocumentTestRest


class TestStopareaRest(BaseDocumentTestRest):
    def setUp(self):
        self.set_prefix_and_model('/stopareas', 'sa', Stoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        # Create a stoparea for testing
        stoparea = Stoparea(
            stoparea_id=1,
            navitia_id='nav1',
            stoparea_name='Stop Area 1',
            line='line1',
            operator='operator1',
        )

        self.session.add(stoparea)
        self.session.flush()

    def test_collection_get(self):
        """Test getting list of stopareas."""
        response = self.app.get('/stopareas', status=200)
        result = response.json

        assert result['total_results'] >= 0
        assert isinstance(result['documents'], list)

    def test_get_stoparea_not_found(self):
        """Test getting a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/999999', status=404)
        result = response.json

        assert result['error'] == 'Stoparea not found'

    def test_get_stoparea_found(self):
        """Test getting a stoparea that exists."""
        response = self.app.get('/stopareas/1', status=200)
        result = response.json

        assert result['id'] == 1
        assert result['navitia_id'] == 'nav1'
        assert result['stoparea_name'] == 'Stop Area 1'
        assert result['line'] == 'line1'
        assert result['operator'] == 'operator1'


class TestStopareaInfoRest(BaseDocumentTestRest):
    def setUp(self):
        self.set_prefix_and_model('/stopareas', 'sa', Stoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        # Create a stoparea for testing
        stoparea = Stoparea(
            stoparea_id=1,
            navitia_id='nav1',
            stoparea_name='Stop Area 1',
            line='line1',
            operator='operator1',
        )

        self.session.add(stoparea)
        self.session.flush()

    def test_get_info_stoparea_not_found(self):
        """Test getting info for a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/999999/fr/info', status=404)
        result = response.json

        assert result['error'] == 'Stoparea not found'

    def test_get_info_stoparea_found(self):
        """Test getting info for a stoparea that exists."""
        response = self.app.get('/stopareas/1/fr/info', status=200)
        result = response.json

        assert result['stoparea_id'] == 1
        assert result['attributes']['navitia_id'] == 'nav1'
        assert result['attributes']['stoparea_name'] == 'Stop Area 1'
        assert result['attributes']['line'] == 'line1'
        assert result['attributes']['operator'] == 'operator1'

    def test_get_info_stoparea_lang_not_found(self):
        """Test getting info for a stoparea that doesn't exist."""
        response = self.app.get('/stopareas/1/invalid/info', status=400)
        result = response.json

        assert result['errors'][0]['description'] == 'invalid lang'


class TestStopareaBboxRest(BaseDocumentTestRest):
    def setUp(self):
        self.set_prefix_and_model('/stopareas', 'sa', Stoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_stoparea(self, stoparea_id, navitia_id, name, line, x, y):
        stoparea = Stoparea(
            stoparea_id=stoparea_id,
            navitia_id=navitia_id,
            stoparea_name=name,
            line=line,
            operator='operator',
            geom=from_shape(Point(x, y), srid=3857),
        )
        self.session.add(stoparea)
        return stoparea

    def _add_test_data(self):
        waypoint = Waypoint(waypoint_type='access', elevation=1000)
        waypoint.locales.append(WaypointLocale(lang='fr', title='Parking du Lac'))
        waypoint.locales.append(WaypointLocale(lang='en', title='Lake car park'))
        self.session.add(waypoint)
        self.session.flush()
        self.waypoint = waypoint

        # a stop is stored once per line: two lines for the same stop
        self._add_stoparea(1, 'nav1', 'Stop 1', 'bus 1', 1000, 1000)
        self._add_stoparea(2, 'nav1', 'Stop 1', 'bus 2', 1000, 1000)
        # stop outside of the bbox used in the tests
        self._add_stoparea(3, 'nav2', 'Stop 2', 'bus 3', 50000, 50000)
        self.session.flush()

        self.session.add(
            WaypointStoparea(
                waypoint_id=waypoint.document_id, stoparea_id=1, distance=1.5
            )
        )
        self.session.add(
            WaypointStoparea(
                waypoint_id=waypoint.document_id, stoparea_id=2, distance=0.5
            )
        )
        self.session.flush()

    def test_bbox_groups_lines_by_stop(self):
        response = self.app.get('/stopareas?bbox=0,0,2000,2000', status=200)
        result = response.json

        assert result['total_results'] == 1
        stop = result['documents'][0]
        assert stop['navitia_id'] == 'nav1'
        assert stop['stoparea_name'] == 'Stop 1'
        assert stop['coordinates'] == {'x': 1000, 'y': 1000}
        assert [line['line'] for line in stop['lines']] == ['bus 1', 'bus 2']

    def test_bbox_answer_can_be_kept_by_the_browsers(self):
        response = self.app.get('/stopareas?bbox=0,0,2000,2000', status=200)

        assert response.headers['Cache-Control'] == 'public, max-age=3600'

    def test_list_without_bbox_is_not_kept(self):
        response = self.app.get('/stopareas', status=200)

        assert 'public' not in response.headers.get('Cache-Control', '')

    def test_bbox_returns_nearest_distance_and_waypoint_titles(self):
        response = self.app.get('/stopareas?bbox=0,0,2000,2000', status=200)
        waypoints = response.json['documents'][0]['waypoints']

        assert len(waypoints) == 1
        assert waypoints[0]['document_id'] == self.waypoint.document_id
        assert waypoints[0]['distance'] == 0.5
        titles = {locale['lang']: locale['title'] for locale in waypoints[0]['locales']}
        assert titles == {'fr': 'Parking du Lac', 'en': 'Lake car park'}

    def test_bbox_without_stop_in_extent(self):
        response = self.app.get(
            '/stopareas?bbox=100000,100000,200000,200000', status=200
        )

        assert response.json['documents'] == []
        assert response.json['total_results'] == 0

    def test_bbox_invalid(self):
        for bbox in ('abc', '1,2,3', '2000,0,0,2000', '0,2000,2000,0', 'nan,0,1,1'):
            self.app.get('/stopareas?bbox=' + bbox, status=400)

    def test_collection_without_bbox_is_unchanged(self):
        response = self.app.get('/stopareas', status=200)

        assert response.json['total_results'] == 3
        assert len(response.json['documents']) == 3
