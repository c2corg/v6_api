import json

from api.models.route import Route, RouteLocale

from .. import BaseTestCase


class TestRouteRest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        response = self.app.get('/routes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = json.loads(response.body)
        self.assertTrue(isinstance(body, list))
        nb_routes = self.session.query(Route).count()
        self.assertEqual(len(body), nb_routes)

    def test_get(self):
        response = self.app.get('/routes/' + str(self.route.document_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = json.loads(response.body)
        self.assertFalse('id' in body)
        self.assertEqual(body.get('document_id'), self.route.document_id)
        self.assertEqual(
            body.get('activities'), self.route.activities)

        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertFalse('id' in locale_en)
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)
        self.assertEqual(locale_en.get('title'), self.locale_en.title)

    def test_post_error(self):
        body = {}
        response = self.app.post(
            '/routes', params=json.dumps(body), expect_errors=True)
        self.assertEqual(response.status_code, 400)

        body = json.loads(response.body)
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'activities is missing')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_missing_title(self):
        body = {
            'activities': 'skitouring',
            'height': 1200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post(
            '/routes', params=json.dumps(body), expect_errors=True,
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
            'activities': 'hiking',
            'height': 750,
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
        }
        response = self.app.post(
            '/routes', params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        route = self.session.query(Route).get(document_id)
        versions = route.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        self.assertEqual(version.culture, 'en')
        self.assertEqual(version.version, 1)
        self.assertEqual(version.nature, 'ft')

        meta_data = version.history_metadata
        self.assertEqual(meta_data.is_minor, False)
        self.assertEqual(meta_data.comment, 'creation')
        self.assertIsNotNone(meta_data.written_at)

        archive_route = version.document_archive
        self.assertEqual(archive_route.document_id, document_id)
        self.assertEqual(archive_route.activities, 'hiking')
        self.assertEqual(archive_route.height, 750)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')
        self.assertEqual(archive_locale.gear, 'shoes')

    def _add_test_data(self):
        self.route = Route(
            activities='paragliding', height=2000)

        self.locale_en = RouteLocale(
            culture='en', title='Mont Blanc from the air', description='...',
            gear='paraglider')

        self.route.locales.append(self.locale_en)

        self.session.add(self.route)
        self.session.flush()
