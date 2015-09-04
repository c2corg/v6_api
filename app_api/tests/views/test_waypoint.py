import json

from .. import BaseTestCase


class TestWaypointRest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()
        # self.config.scan('app_api.views.summit')

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
                {'culture': 'en', 'title': 'Mont Pourri'}
            ]
        }
        response = self.app.post(
            '/waypoints', params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)

    def _add_test_data(self):
        from app_api.models.waypoint import Waypoint, WaypointLocale
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)

        self.locale_en = WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            pedestrian_access='yep')

        self.waypoint.locales.append(self.locale_en)

        self.session.add(self.waypoint)
        self.session.flush()
