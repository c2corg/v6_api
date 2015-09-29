from c2corg_api.models.route import Route, RouteLocale

from c2corg_api.tests.views import BaseTestRest


class TestRouteRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model("/routes", Route)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        body = self.get(self.route)
        self.assertEqual(
            body.get('activities'), self.route.activities)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertMissing(errors[0], 'activities')

    def test_post_missing_title(self):
        body = {
            'activities': 'skitouring',
            'height': 1200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        response = self.app.post_json(
            '/routes', body, expect_errors=True, status=400)

        body = response.json
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
        body, doc = self.post_success(body)
        version = doc.versions[0]

        archive_route = version.document_archive
        self.assertEqual(archive_route.activities, 'hiking')
        self.assertEqual(archive_route.height, 750)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

    def _add_test_data(self):
        self.route = Route(
            activities='paragliding', height=2000)

        self.locale_en = RouteLocale(
            culture='en', title='Mont Blanc from the air', description='...',
            gear='paraglider')

        self.locale_fr = RouteLocale(
            culture='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider')

        self.route.locales.append(self.locale_en)
        self.route.locales.append(self.locale_fr)

        self.session.add(self.route)
        self.session.flush()
