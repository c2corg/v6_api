import json

from app_api.models.waypoint import Waypoint, WaypointLocale

from .. import BaseTestCase


class TestWaypointRest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_get(self):
        response = self.app.get('/waypoints/' + str(self.waypoint.document_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = json.loads(response.body)
        self.assertFalse('id' in body)
        self.assertEqual(body.get('document_id'), self.waypoint.document_id)
        self.assertEqual(
            body.get('waypoint_type'), self.waypoint.waypoint_type)

        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertFalse('id' in locale_en)
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)
        self.assertEqual(locale_en.get('title'), self.locale_en.title)

    def test_post_error(self):
        body = {}
        response = self.app.post(
            '/waypoints', params=json.dumps(body), expect_errors=True)
        self.assertEqual(response.status_code, 400)

        body = json.loads(response.body)
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'waypoint_type is missing')
        self.assertEqual(errors[0].get('name'), 'waypoint_type')

    def test_post_missing_title(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post(
            '/waypoints', params=json.dumps(body), expect_errors=True,
            content_type='application/json')
        self.assertEqual(response.status_code, 400)

        body = json.loads(response.body)
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
        response = self.app.post(
            '/waypoints', params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        waypoint = self.session.query(Waypoint).get(document_id)
        versions = waypoint.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        self.assertEqual(version.culture, 'en')
        self.assertEqual(version.version, 1)
        self.assertEqual(version.nature, 'ft')

        meta_data = version.history_metadata
        self.assertEqual(meta_data.is_minor, False)
        self.assertEqual(meta_data.comment, 'creation')
        self.assertIsNotNone(meta_data.written_at)

        archive_waypoint = version.document_archive
        self.assertEqual(archive_waypoint.document_id, document_id)
        self.assertEqual(archive_waypoint.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint.elevation, 3779)

        archive_locale = version.document_i18n_archive
        self.assertEqual(archive_locale.document_id, document_id)
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
