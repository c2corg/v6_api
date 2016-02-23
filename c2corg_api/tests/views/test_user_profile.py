import json

from c2corg_api.models.user_profile import UserProfile, ArchiveUserProfile
from shapely.geometry import shape, Point

from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestUserProfileRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/profiles', UserProfile, ArchiveUserProfile,
            ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection_unauthenticated(self):
        self.app.get(self._prefix, status=403)

    def test_get_collection(self):
        body = self.get_collection(user='contributor')
        doc = body['documents'][0]
        self.assertIn('areas', doc)

    def test_get_collection_paginated(self):
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 0}, user='contributor'),
            [], 4)

        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 1}, user='contributor'),
            [self.profile4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 2}, user='contributor'),
            [self.profile4.document_id, self.profile3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 1, 'limit': 2}, user='contributor'),
            [self.profile3.document_id, self.profile2.document_id], 4)

        self.assertResultsEqual(
            self.get_collection(
                {'after': self.profile3.document_id, 'limit': 1},
                user='contributor'),
            [self.profile2.document_id], -1)

    def test_get_collection_lang(self):
        self.get_collection_lang(user='contributor')

    def test_get_unauthenticated(self):
        self.app.get(
            self._prefix + '/' + str(self.profile1.document_id), status=403)

    def test_get(self):
        body = self.get(self.profile1, user='contributor')
        self._assert_geometry(body)

    def test_get_lang(self):
        self.get_lang(self.profile1, user='contributor')

    def test_get_new_lang(self):
        self.get_new_lang(self.profile1, user='contributor')

    def test_get_404(self):
        self.get_404(user='contributor')

    def test_no_post(self):
        # can not create new profiles
        self.app.post_json(
            self._prefix, {}, expect_errors=True, status=404)

    # TODO add test that checks that user can only change its own profile

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.profile1.version,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': -9999,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(
            body, self.profile1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(
            body, self.profile1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(
            body, self.profile1.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(
            self.profile1.document_id, user='moderator')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.profile1.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}'  # noqa
                }
            }
        }
        (body, profile) = self.put_success_all(
            body, self.profile1, user='moderator')

        # version with lang 'en'
        version_en = profile.versions[2]

        # geometry has been changed
        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'pro',
                'locales': [
                    {'lang': 'en', 'title': 'Me',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, profile) = self.put_success_figures_only(
            body, self.profile1, user='moderator')

        self.assertEquals(profile.category, 'pro')

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'amateur',
                'locales': [
                    {'lang': 'en', 'title': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, profile) = self.put_success_lang_only(
            body, self.profile1, user='moderator')

        self.assertEquals(
            profile.get_locale('en').title, 'Me!')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'category': 'amateur',
                'locales': [
                    {'lang': 'es', 'title': 'Yo'}
                ]
            }
        }
        (body, profile) = self.put_success_new_lang(
            body, self.profile1, user='moderator')

        self.assertEquals(profile.get_locale('es').title, 'Yo')

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom'))

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        self.assertIsInstance(point, Point)

    def _add_test_data(self):
        user_id = self.global_userids['contributor']
        self.profile1 = UserProfile(category='amateur')

        self.locale_en = DocumentLocale(lang='en', title='Me')
        self.locale_fr = DocumentLocale(lang='fr', title='Moi')

        self.profile1.locales.append(self.locale_en)
        self.profile1.locales.append(self.locale_fr)

        self.profile1.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')

        self.session.add(self.profile1)
        self.session.flush()

        DocumentRest(None)._create_new_version(self.profile1, user_id)

        self.profile2 = UserProfile(category='amateur')
        self.session.add(self.profile2)
        self.profile3 = UserProfile(category='amateur')
        self.session.add(self.profile3)
        self.profile4 = UserProfile(category='amateur')
        self.profile4.locales.append(DocumentLocale(
            lang='en', title='You'))
        self.profile4.locales.append(DocumentLocale(
            lang='fr', title='Toi'))
        self.session.add(self.profile4)

        self.session.flush()
