from c2corg_api.models.waypoint import Waypoint, WaypointLocale

from c2corg_api.tests.views import BaseTestRest


class TestWaypointRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model("/waypoints", Waypoint)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        self.get(self.waypoint)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertMissing(errors[0], 'waypoint_type')

    def test_post_missing_title(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post_json(
            '/waypoints', body, expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'locales.0.title')

    def test_post_success(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {'culture': 'en', 'title': 'Mont Pourri',
                 'pedestrian_access': 'y'}
            ]
        }
        body, doc = self.post_success(body)
        version = doc.versions[0]

        archive_waypoint = version.document_archive
        self.assertEqual(archive_waypoint.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint.elevation, 3779)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Mont Pourri')
        self.assertEqual(archive_locale.pedestrian_access, 'y')

    def _add_test_data(self):
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)

        self.locale_en = WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            pedestrian_access='yep')

        self.waypoint.locales.append(self.locale_en)

        self.session.add(self.waypoint)
        self.session.flush()
