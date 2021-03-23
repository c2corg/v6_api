import json

from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile, ArchiveUserProfile, \
    USERPROFILE_TYPE
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.tests.search import reset_search_index
from c2corg_api.models.common.attributes import quality_types
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
        self.assertIn('name', doc)
        self.assertNotIn('username', doc)
        self.assertNotIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 0}, user='contributor'),
            [], 7)

        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 1}, user='contributor'),
            [self.profile4.document_id], 7)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 0, 'limit': 2}, user='contributor'),
            [self.profile4.document_id, self.profile2.document_id], 7)
        self.assertResultsEqual(
            self.get_collection(
                {'offset': 1, 'limit': 3}, user='contributor'),
            [self.profile2.document_id, self.global_userids['contributor3'],
             self.global_userids['contributor2']], 7)

    def test_get_collection_lang(self):
        self.get_collection_lang(user='contributor')

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}, user='contributor'),
            [self.profile4.document_id, self.global_userids['contributor3'],
             self.global_userids['contributor2'], self.profile1.document_id,
             self.global_userids['moderator'], self.global_userids['robot']],
            6)

    def test_get_unauthenticated_private_profile(self):
        """Tests that only the user name is returned when requesting a private
        profile unauthenticated.
        """
        response = self.app.get(self._prefix + '/' +
                                str(self.profile1.document_id),
                                status=200)
        body = response.json

        self.assertEqual(body.get('not_authorized'), True)
        self.assertNotIn('username', body)
        self.assertIn('name', body)
        self.assertNotIn('locales', body)
        self.assertNotIn('geometry', body)

    def test_get_unauthenticated_public_profile(self):
        """Tests that the full profile is returned when requesting a public
        profile when unauthenticated.
        """
        contributor = self.profile1.user
        contributor.is_profile_public = True
        self.session.flush()

        body = self.get(self.profile1, check_title=False)
        self.assertNotIn('username', body)
        self.assertIn('name', body)
        self.assertIn('locales', body)
        self.assertIn('geometry', body)

    def test_get(self):
        body = self.get(self.profile1, user='contributor', check_title=False)
        self._assert_geometry(body)
        self.assertIsNone(body['locales'][0].get('title'))
        self.assertNotIn('maps', body)
        self.assertNotIn('username', body)
        self.assertIn('name', body)
        self.assertIn('forum_username', body)

    def test_get_unconfirmed_user(self):
        headers = self.add_authorization_header(username='contributor')
        self.app.get(self._prefix + '/' + str(self.profile3.document_id),
                     headers=headers, status=404)

    def test_get_cooked(self):
        self.get_cooked(self.profile1, user='contributor')

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.profile1, user='contributor')

    def test_get_lang(self):
        self.get_lang(self.profile1, user='contributor')

    def test_get_new_lang(self):
        self.get_new_lang(self.profile1, user='contributor')

    def test_get_404(self):
        self.get_404(user='contributor')

    def test_get_caching(self):
        self.get_caching(self.profile1, user='contributor')

    def test_get_info(self):
        body, locale = self.get_info(self.profile1, 'en')
        self.assertEqual(locale.get('lang'), 'en')
        self.assertEqual(locale.get('title'), 'Contributor')

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
                'document_id': '9999999',
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
            body, self.profile1, user='moderator', check_es=False,
            cache_version=3)

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

        self.assertEqual(profile.categories, ['mountain_guide'])
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

        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(profile.get_locale('es').description, 'Yo')
        search_doc = self._check_es_index()
        self.assertEqual(
            search_doc['title_es'], 'Contributor contributor')

    def _check_es_index(self):
        sync_es(self.session)
        search_doc = SearchUser.get(
            id=self.profile1.document_id,
            index=elasticsearch_config['index'])
        self.assertEqual(search_doc['doc_type'], self.profile1.type)
        self.assertEqual(
            search_doc['title_en'], 'Contributor contributor')
        self.assertEqual(
            search_doc['title_fr'], 'Contributor contributor')
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

        # create users for the profiles
        self.user2 = User(
            name='user2', username='user2', email='user2@c2c.org',
            forum_username='user2', password='pass',
            email_validated=True, profile=self.profile2)
        self.user3 = User(
            name='user3', username='user3', email='user3@c2c.org',
            forum_username='user3', password='pass',
            email_validated=False, profile=self.profile3)
        self.user4 = User(
            name='user4', username='user4', email='user4@c2c.org',
            forum_username='user4', password='pass',
            email_validated=True, profile=self.profile4)
        self.session.add_all([self.user2, self.user3, self.user4])

        self.session.flush()
