import json

from c2corg_api.tests.search import reset_search_index
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, Point

from c2corg_api.models.image import Image, ArchiveImage, IMAGE_TYPE
from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestImageRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/images", IMAGE_TYPE, Image, ArchiveImage, ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertIn('filename', doc)
        self.assertNotIn('file_size', doc)

    def test_get_collection_paginated(self):
        self.app.get("/images?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.image4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.image4.document_id, self.image3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.image3.document_id, self.image2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.image4.document_id, self.image.document_id], 2)

    def test_get(self):
        body = self.get(self.image)
        self._assert_geometry(body)
        self.assertNotIn('maps', body)

    def test_get_lang(self):
        self.get_lang(self.image)

    def test_get_new_lang(self):
        self.get_new_lang(self.image)

    def test_get_404(self):
        self.get_404()

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales')
        self.assertCorniceRequired(errors[1], 'image_type')

    def test_post_missing_title(self):
        body_post = {
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'locales': [
                {'lang': 'en'}
            ]
        }
        body = self.post_missing_title(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'protected': True,
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop'}
            ]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body)

        version = doc.versions[0]

        archive_image = version.document_archive
        self.assertEqual(archive_image.activities, ['paragliding'])
        self.assertEqual(archive_image.height, 1500)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.image.version,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
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
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
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
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
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
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.image.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.image.document_id)

    def test_put_wrong_user(self):
        """Test that a non-moderator user who is not the creator of
        a personal image is not allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'activities': ['skitouring'],
                'image_type': 'personal',
                'height': 2000,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': 'A nice picture',
                     'version': self.image4.get_locale('en').version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor2')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id), body,
            headers=headers, status=403)

    def test_put_good_user(self):
        """Test that a non-moderator user who is the creator of
        a personal image is allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'image_type': 'personal',
                'height': 2000,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': 'A nice picture',
                     'version': self.image4.get_locale('en').version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id), body,
            headers=headers, status=200)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'geometry': {
                    'version': self.image.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [1, 2]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': 'New description',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, image) = self.put_success_all(body, self.image)

        self.assertEquals(image.height, 2000)
        locale_en = image.get_locale('en')
        self.assertEquals(locale_en.description, 'New description')

        # version with lang 'en'
        versions = image.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['paragliding'])
        self.assertEqual(archive_document_en.height, 2000)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, image) = self.put_success_figures_only(body, self.image)

        self.assertEquals(image.height, 2000)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
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
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...'}
                ]
            }
        }
        (body, image) = self.put_success_new_lang(body, self.image)

        self.assertEquals(image.get_locale('es').description, '...')

    def test_change_image_type_collaborative(self):
        """Test that a non-moderator user cannot change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id), body,
            headers=headers, status=400)

    def test_change_image_type_collaborative_moderator(self):
        """Test that a moderator can change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id), body,
            headers=headers, status=200)

    def test_change_image_type_non_collaborative(self):
        """Test that non collaborative images can become collaborative
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...',
                     'version': self.image4.get_locale('en').version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id), body,
            headers=headers, status=200)

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
            activities=['paragliding'], height=1500,
            image_type='collaborative')

        self.locale_en = DocumentLocale(
            lang='en', title='Mont Blanc from the air', description='...')

        self.locale_fr = DocumentLocale(
            lang='fr', title='Mont Blanc du ciel', description='...')

        self.image.locales.append(self.locale_en)
        self.image.locales.append(self.locale_fr)

        self.image.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')

        self.session.add(self.image)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.image, user_id)

        self.image2 = Image(
            activities=['paragliding'], height=1500)
        self.session.add(self.image2)
        self.image3 = Image(
            activities=['paragliding'], height=1500)
        self.session.add(self.image3)
        self.image4 = Image(
            activities=['paragliding'], height=1500,
            image_type='personal')
        self.image4.locales.append(DocumentLocale(
            lang='en', title='Mont Blanc from the air', description='...'))
        self.image4.locales.append(DocumentLocale(
            lang='fr', title='Mont Blanc du ciel', description='...'))
        self.session.add(self.image4)
        self.session.flush()
        DocumentRest.create_new_version(self.image4, user_id)
