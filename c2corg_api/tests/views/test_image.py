import json
from shapely.geometry import shape, Point

from c2corg_api.models.image import (
    Image, ImageLocale, ArchiveImage, ArchiveImageLocale)
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseTestRest


class TestImageRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/images", Image, ArchiveImage, ArchiveImageLocale)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        body = self.get(self.image)
        self._assert_geometry(body)

    def test_get_lang(self):
        self.get_lang(self.image)

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
                {'culture': 'en', 'title': 'Some nice loop'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'activities': 'hiking',
            'height': 750,
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop'}
            ]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body)

        version = doc.versions[0]

        archive_image = version.document_archive
        self.assertEqual(archive_image.activities, 'hiking')
        self.assertEqual(archive_image.height, 750)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': -9999,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.image.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.image.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.image.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.image.document_id)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 1500,
                'geometry': {
                    'version': self.image.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [1, 2]}'
                },
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': 'New description',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, image) = self.put_success_all(body, self.image)

        self.assertEquals(image.height, 1500)
        locale_en = image.get_locale('en')
        self.assertEquals(locale_en.description, 'New description')

        # version with culture 'en'
        versions = image.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, 'paragliding')
        self.assertEqual(archive_document_en.height, 1500)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with culture 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 1500,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, image) = self.put_success_figures_only(body, self.image)

        self.assertEquals(image.height, 1500)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 2000,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': 'New description',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, image) = self.put_success_lang_only(body, self.image)

        self.assertEquals(
            image.get_locale('en').description, 'New description')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'activities': 'paragliding',
                'height': 2000,
                'locales': [
                    {'culture': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...'}
                ]
            }
        }
        (body, image) = self.put_success_new_lang(body, self.image)

        self.assertEquals(image.get_locale('es').description, '...')

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom'))

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        self.assertIsInstance(point, Point)
        self.assertAlmostEqual(point.x, 635956)
        self.assertAlmostEqual(point.y, 5723604)

    def _add_test_data(self):
        self.image = Image(
            activities='paragliding', height=2000)

        self.locale_en = ImageLocale(
            culture='en', title='Mont Blanc from the air', description='...')

        self.locale_fr = ImageLocale(
            culture='fr', title='Mont Blanc du ciel', description='...')

        self.image.locales.append(self.locale_en)
        self.image.locales.append(self.locale_fr)

        self.image.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')

        self.session.add(self.image)
        self.session.flush()

        DocumentRest(None)._create_new_version(self.image)
