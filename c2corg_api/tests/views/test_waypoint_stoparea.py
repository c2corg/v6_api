from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale)
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea

from c2corg_api.tests.views import BaseDocumentTestRest


class TestWaypointStopareaRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/waypoints_stopareas", "ws", WaypointStoparea, None, None)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        # Create waypoints for testing
        waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=3779
        )

        locale_en = WaypointLocale(
            lang='en', title='Mont Pourri', access='y')
        waypoint1.locales.append(locale_en)

        self.session.add(waypoint1)
        self.session.flush()
        self.waypoint1 = waypoint1

        waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=3000
        )

        locale_en2 = WaypointLocale(
            lang='en', title='Another Summit', access='y')
        waypoint2.locales.append(locale_en2)

        self.session.add(waypoint2)
        self.session.flush()
        self.waypoint2 = waypoint2

        # Create stopareas for testing
        stoparea1 = Stoparea(
            stoparea_id=1,
            navitia_id='nav1',
            stoparea_name='Stop Area 1',
            line='line1',
            operator='operator1'
        )

        self.session.add(stoparea1)
        self.session.flush()
        self.stoparea1 = stoparea1

        stoparea2 = Stoparea(
            stoparea_id=2,
            navitia_id='nav2',
            stoparea_name='Stop Area 2',
            line='line2',
            operator='operator2'
        )

        self.session.add(stoparea2)
        self.session.flush()
        self.stoparea2 = stoparea2

        # Create waypoint-stoparea associations
        waypoint_stoparea1 = WaypointStoparea(
            waypoint_stoparea_id=1,
            waypoint_id=waypoint1.document_id,
            stoparea_id=stoparea1.stoparea_id,
            distance=100.0
        )

        self.session.add(waypoint_stoparea1)
        self.session.flush()
        self.waypoint_stoparea1 = waypoint_stoparea1

        waypoint_stoparea2 = WaypointStoparea(
            waypoint_stoparea_id=2,
            waypoint_id=waypoint1.document_id,
            stoparea_id=stoparea2.stoparea_id,
            distance=200.0
        )

        self.session.add(waypoint_stoparea2)
        self.session.flush()
        self.waypoint_stoparea2 = waypoint_stoparea2

    def test_get_stopareas_by_waypoint(self):
        """Test getting stopareas for a waypoint"""
        response = self.app.get('/waypoints/{}/stopareas'.format(
            self.waypoint1.document_id), status=200)
        result = response.json

        self.assertEqual(result['waypoint_id'], self.waypoint1.document_id)
        self.assertEqual(len(result['stopareas']), 2)

        stoparea1 = result['stopareas'][0]
        self.assertEqual(stoparea1['id'], 1)
        self.assertEqual(stoparea1['navitia_id'], 'nav1')
        self.assertEqual(stoparea1['stoparea_name'], 'Stop Area 1')
        self.assertEqual(stoparea1['line'], 'line1')
        self.assertEqual(stoparea1['operator'], 'operator1')
        self.assertEqual(stoparea1['distance'], 100.0)

        stoparea2 = result['stopareas'][1]
        self.assertEqual(stoparea2['id'], 2)
        self.assertEqual(stoparea2['navitia_id'], 'nav2')
        self.assertEqual(stoparea2['stoparea_name'], 'Stop Area 2')
        self.assertEqual(stoparea2['line'], 'line2')
        self.assertEqual(stoparea2['operator'], 'operator2')
        self.assertEqual(stoparea2['distance'], 200.0)

    def test_get_stopareas_by_waypoint_not_found(self):
        """Test getting stopareas for a waypoint that doesn't exist"""
        # We'll test that it returns an empty array instead of 404
        response = self.app.get('/waypoints/999999/stopareas', status=200)
        result = response.json

        self.assertEqual(result['waypoint_id'], 999999)
        self.assertEqual(result['stopareas'], [])

    def test_get_is_reachable_true(self):
        """Test checking if a waypoint is reachable (has stopareas)"""
        response = self.app.get('/waypoints/{}/isReachable'.format(
            self.waypoint1.document_id), status=200)
        result = response.json

        self.assertTrue(result)

    def test_get_is_reachable_false(self):
        """Test checking if a waypoint is not reachable (no stopareas)"""
        response = self.app.get('/waypoints/{}/isReachable'.format(
            self.waypoint2.document_id), status=200)
        result = response.json

        self.assertFalse(result)

    def test_get_info(self):
        """Test getting info for a waypoint-stoparea"""

        response = self.app.get(
            '/waypoints_stopareas/1/en/info', status=200)
        result = response.json

        self.assertEqual(
            result['waypoint_stoparea_id'],
            self.waypoint_stoparea1.waypoint_stoparea_id
        )
        self.assertEqual(
            result['attributes']['distance'],
            100.0
        )
        self.assertEqual(
            result['attributes']['waypoint_id'],
            self.waypoint1.document_id
        )
        self.assertEqual(result['attributes']['stoparea_id'], 1)

    def test_get_info_not_found(self):
        """Test getting info for a waypoint-stoparea that doesn't exist"""
        response = self.app.get(
            '/waypoints_stopareas/999999/en/info', status=404)
        self.assertEqual(
            response.json_body,
            {'error': 'Waypoint Stoparea not found'}
        )

    def test_get_info_lang_not_found(self):
        """Test getting info for a waypoint-stoparea
        that exist with an invalid lang"""
        response = self.app.get(
            '/waypoints_stopareas/1/invalid/info', status=400)

        # Updated to match actual JSON response format
        self.assertEqual(
            response.json_body['errors'][0]['description'],
            "invalid lang"
        )
