import json

from c2corg_api.models.user_profile import UserProfile, ArchiveUserProfile, \
    USERPROFILE_TYPE
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, Point

from c2corg_api.models.document import (
    ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestUserProfileRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/profiles', USERPROFILE_TYPE, UserProfile, ArchiveUserProfile,
            ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection_unauthenticated(self):
        self.app.get(self._prefix, status=403)

    def test_get_collection(self):
        body = self.get_collection(user='contributor')
        doc = body['documents'][0]
        self.assertIn('areas', doc)
        self.assertIn('username', doc)
        self.assertNotIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 0}, user='contributor'),
            [], 6)

        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 1}, user='contributor'),
            [self.profile4.document_id], 6)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 2}, user='contributor'),
            [self.profile4.document_id, self.profile3.document_id], 6)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 1, 'limit': 2}, user='contributor'),
            [self.profile3.document_id, self.profile2.document_id], 6)

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
        body = self.get(self.profile1, user='contributor', check_title=False)
        self._assert_geometry(body)
        self.assertIsNone(body['locales'][0].get('title'))
        self.assertNotIn('maps', body)
        self.assertIn('username', body)

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

    def test_put_wrong_user(self):
        """Test that a normal user can only edit its own profile.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.profile1.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}'  # noqa
                }
            }
        }

        headers = self.add_authorization_header(username='contributor2')
        self.app_put_json(
            self._prefix + '/' + str(self.profile1.document_id), body,
            headers=headers, status=403)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
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
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
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
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
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
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
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
                'quality': quality_types[1],
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.profile1.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}'  # noqa
                }
            }
        }
        (body, profile) = self.put_success_all(
            body, self.profile1, user='moderator', check_es=False)

        # version with lang 'en'
        version_en = profile.versions[2]

        # geometry has been changed
        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        self._check_es_index()

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['mountain_guide'],
                'locales': [
                    {'lang': 'en', 'description': 'Me',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, profile) = self.put_success_figures_only(
            body, self.profile1, user='moderator', check_es=False)

        self.assertEquals(profile.categories, ['mountain_guide'])
        self._check_es_index()

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [
                    {'lang': 'en', 'description': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, profile) = self.put_success_lang_only(
            body, self.profile1, user='moderator', check_es=False)

        self.assertEquals(
            profile.get_locale('en').description, 'Me!')
        self._check_es_index()

    def test_put_reset_title(self):
        """Tests that the title can not be set.
        """
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [
                    {'lang': 'en', 'title': 'Should not be set',
                     'description': 'Me!',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, profile) = self.put_success_lang_only(
            body, self.profile1, user='moderator', check_es=False)

        self.assertEquals(
            profile.get_locale('en').description, 'Me!')
        self.session.refresh(self.locale_en)
        self.assertEqual(self.locale_en.title, '')

        # check that the the user names are added to the search index
        self._check_es_index()

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [
                    {'lang': 'es', 'description': 'Yo'}
                ]
            }
        }
        (body, profile) = self.put_success_new_lang(
            body, self.profile1, user='moderator', check_es=False)

        self.assertEquals(profile.get_locale('es').description, 'Yo')
        search_doc = self._check_es_index()
        self.assertEqual(search_doc['title_es'], 'contributor Contributor')

    def _check_es_index(self):
        sync_es(self.session)
        search_doc = SearchUser.get(
            id=self.profile1.document_id,
            index=elasticsearch_config['index'])
        self.assertEqual(search_doc['doc_type'], self.profile1.type)
        self.assertEqual(search_doc['title_en'], 'contributor Contributor')
        self.assertEqual(search_doc['title_fr'], 'contributor Contributor')
        return search_doc

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
        self.profile1 = self.session.query(UserProfile).get(user_id)
        self.locale_en = self.profile1.get_locale('en')
        self.locale_fr = self.profile1.get_locale('fr')
        DocumentRest.create_new_version(self.profile1, user_id)

        self.profile2 = UserProfile(categories=['amateur'])
        self.session.add(self.profile2)
        self.profile3 = UserProfile(categories=['amateur'])
        self.session.add(self.profile3)
        self.profile4 = UserProfile(categories=['amateur'])
        self.profile4.locales.append(DocumentLocale(
            lang='en', description='You', title=''))
        self.profile4.locales.append(DocumentLocale(
            lang='fr', description='Toi', title=''))
        self.session.add(self.profile4)

        self.session.flush()
