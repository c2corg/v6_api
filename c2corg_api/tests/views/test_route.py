from c2corg_api.models.route import (
    Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseTestRest


class TestRouteRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/routes", Route, ArchiveRoute, ArchiveRouteLocale)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        body = self.get(self.route)
        self.assertEqual(
            body.get('activities'), self.route.activities)

    def test_get_lang(self):
        self.get_lang(self.route)

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
        self.post_missing_title(body)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'activities': 'hiking',
            'height': 750,
            'protected': True,
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

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

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version_hash': 'some-old-version',
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': 'some-old-version'}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        self.put_wrong_ids(body, self.route.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.route.document_id)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        (body, route) = self.put_success_all(body, self.route)

        self.assertEquals(route.height, 1500)
        locale_en = route.get_locale('en')
        self.assertEquals(locale_en.description, '...')
        self.assertEquals(locale_en.gear, 'none')

        # version with culture 'en'
        versions = route.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')
        self.assertEqual(archive_locale.gear, 'none')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, 'paragliding')
        self.assertEqual(archive_document_en.height, 1500)

        # version with culture 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')
        self.assertEqual(archive_locale.gear, 'paraglider')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)

        self.assertEquals(route.height, 1500)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 2000,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        (body, route) = self.put_success_lang_only(body, self.route)

        self.assertEquals(route.get_locale('en').gear, 'none')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.route.document_id,
                'version_hash': self.route.version_hash,
                'activities': 'paragliding',
                'height': 2000,
                'locales': [
                    {'culture': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...', 'gear': 'si'}
                ]
            }
        }
        (body, route) = self.put_success_new_lang(body, self.route)

        self.assertEquals(route.get_locale('es').gear, 'si')

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

        DocumentRest(None)._create_new_version(self.route)
