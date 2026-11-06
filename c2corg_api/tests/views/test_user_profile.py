import json

import pytest
from shapely.geometry import Point, shape

from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import ArchiveDocumentLocale, DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import (
    USERPROFILE_TYPE,
    ArchiveUserProfile,
    UserProfile,
)
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.user_mapping import SearchUser
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType

PROFILES = DocType(
    '/profiles',
    USERPROFILE_TYPE,
    UserProfile,
    ArchiveUserProfile,
    ArchiveDocumentLocale,
)


class TestUserProfileRest:
    @pytest.fixture(autouse=True)
    def _setup_test_user_profile_rest(self, client, session, user_ids):
        self._add_test_data(session, user_ids)

    def test_get_collection_unauthenticated(self, client):
        response = client.get(PROFILES.prefix, status=403)
        # the message of Pyramid in production (without debug_authorization)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'Forbidden',
                'description': 'Authentication required',
            }
        ]

    def test_get_collection(self, client, session):
        body = scenarios.get_collection(client, session, PROFILES, user='contributor')
        doc = body['documents'][0]
        assert 'areas' in doc
        assert 'name' in doc
        assert 'username' not in doc
        assert 'geometry' not in doc

    def test_get_collection_paginated(self, client, session, user_ids):
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client,
                session,
                PROFILES,
                {'offset': 0, 'limit': 0},
                user='contributor',
            ),
            [],
            8,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection(
                client,
                session,
                PROFILES,
                {'offset': 0, 'limit': 1},
                user='contributor',
            ),
            [self.profile4.document_id],
            8,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client,
                session,
                PROFILES,
                {'offset': 0, 'limit': 2},
                user='contributor',
            ),
            [self.profile4.document_id, self.profile2.document_id],
            8,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client,
                session,
                PROFILES,
                {'offset': 1, 'limit': 3},
                user='contributor',
            ),
            [
                self.profile2.document_id,
                user_ids['contributornotos'],
                user_ids['contributor3'],
            ],
            8,
        )

    def test_get_collection_lang(self, client):
        scenarios.get_collection_lang(client, PROFILES, user='contributor')

    def test_get_collection_search(self, client, session, user_ids):
        reset_search_index(session)

        scenarios.assert_results_equal(
            scenarios.get_collection_search(
                client, PROFILES, {'l': 'en'}, user='contributor'
            ),
            [
                self.profile4.document_id,
                user_ids['contributornotos'],
                user_ids['contributor3'],
                user_ids['contributor2'],
                self.profile1.document_id,
                user_ids['moderator'],
                user_ids['robot'],
            ],
            7,
        )

    def test_get_unauthenticated_private_profile(self, client):
        """Tests that only the user name is returned when requesting a private
        profile unauthenticated.
        """
        response = client.get(
            PROFILES.prefix + '/' + str(self.profile1.document_id), status=200
        )
        body = response.json

        assert body.get('not_authorized') is True
        assert 'username' not in body
        assert 'name' in body
        assert 'locales' not in body
        assert 'geometry' not in body

    def test_get_unauthenticated_public_profile(self, client, session):
        """Tests that the full profile is returned when requesting a public
        profile when unauthenticated.
        """
        contributor = self.profile1.user
        contributor.is_profile_public = True
        session.flush()

        body = scenarios.get(client, PROFILES, self.profile1)
        assert 'username' not in body
        assert 'name' in body
        assert 'locales' in body
        assert 'geometry' in body

    def test_get(self, client):
        body = scenarios.get(client, PROFILES, self.profile1, user='contributor')
        self._assert_geometry(body)
        assert body['license']['id'] == 'CC-BY-NC-ND-3.0'
        assert body['license']['attribution_url'].startswith(
            f'http://localhost:6553/profiles/history/{self.profile1.document_id}/'
        )
        assert body['locales'][0].get('title') is None
        assert 'maps' not in body
        assert 'username' not in body
        assert 'name' in body
        assert 'forum_username' in body

    def test_get_unconfirmed_user(self, client):
        headers = auth_headers(username='contributor')
        client.get(
            PROFILES.prefix + '/' + str(self.profile3.document_id),
            headers=headers,
            status=404,
        )

    def test_get_cooked(self, client):
        scenarios.get_cooked(client, PROFILES, self.profile1, user='contributor')

    def test_get_cooked_with_defaulting(self, client):
        scenarios.get_cooked_with_defaulting(
            client, PROFILES, self.profile1, user='contributor'
        )

    def test_get_lang(self, client):
        scenarios.get_lang(client, PROFILES, self.profile1, user='contributor')

    def test_get_new_lang(self, client):
        scenarios.get_new_lang(client, PROFILES, self.profile1, user='contributor')

    def test_get_404(self, client):
        scenarios.get_404(client, PROFILES, user='contributor')

    def test_get_caching(self, client):
        scenarios.get_caching(client, PROFILES, self.profile1, user='contributor')

    def test_get_info(self, client):
        body, locale = scenarios.get_info(client, PROFILES, self.profile1, 'en')
        assert locale.get('lang') == 'en'
        assert locale.get('title') == 'Contributor'

    def test_no_post(self, client):
        # can not create new profiles
        client.post_json(PROFILES.prefix, {}, status=405)

    def test_put_wrong_user(self, client):
        """Test that a normal user can only edit its own profile."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.profile1.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
                },
            },
        }

        headers = auth_headers(username='contributor2')
        send_json(
            client,
            'put',
            PROFILES.prefix + '/' + str(self.profile1.document_id),
            body,
            headers=headers,
            status=403,
        )

    def test_put_wrong_document_id(self, client):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_document_id(client, PROFILES, body, user='moderator')

    def test_put_wrong_document_version(self, client):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': -9999,
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_version(
            client, PROFILES, body, self.profile1.document_id, user='moderator'
        )

    def test_put_wrong_locale_version(self, client):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [{'lang': 'en', 'description': 'Me!', 'version': -9999}],
            }
        }
        scenarios.put_wrong_version(
            client, PROFILES, body, self.profile1.document_id, user='moderator'
        )

    def test_put_wrong_ids(self, client):
        body = {
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_ids(
            client, PROFILES, body, self.profile1.document_id, user='moderator'
        )

    def test_put_no_document(self, client):
        scenarios.put_no_document(
            client, PROFILES, self.profile1.document_id, user='moderator'
        )

    def test_put_success_all(self, client, session):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.profile1.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
                },
            },
        }
        (body, profile) = scenarios.put_success_all(
            client,
            session,
            PROFILES,
            body,
            self.profile1,
            user='moderator',
            check_es=False,
            cache_version=3,
            locale_fr=self.locale_fr,
        )

        # version with lang 'en'
        version_en = profile.versions[2]

        # geometry has been changed
        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        self._check_es_index(session)

    def test_put_success_figures_only(self, client, session):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, profile) = scenarios.put_success_figures_only(
            client,
            session,
            PROFILES,
            body,
            self.profile1,
            user='moderator',
            check_es=False,
        )

        assert profile.categories == ['mountain_guide']
        self._check_es_index(session)

    def test_put_success_lang_only(self, client, session):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, profile) = scenarios.put_success_lang_only(
            client,
            session,
            PROFILES,
            body,
            self.profile1,
            user='moderator',
            check_es=False,
        )

        assert profile.get_locale('en').description == 'Me!'
        self._check_es_index(session)

    def test_put_reset_title(self, client, session):
        """Tests that the title can not be set."""
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Should not be set',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, profile) = scenarios.put_success_lang_only(
            client,
            session,
            PROFILES,
            body,
            self.profile1,
            user='moderator',
            check_es=False,
        )

        assert profile.get_locale('en').description == 'Me!'
        session.refresh(self.locale_en)
        assert self.locale_en.title == ''

        # check that the the user names are added to the search index
        self._check_es_index(session)

    def test_put_success_new_lang(self, client, session):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': quality_types[1],
                'categories': ['amateur'],
                'locales': [{'lang': 'es', 'description': 'Yo'}],
            },
        }
        (body, profile) = scenarios.put_success_new_lang(
            client,
            session,
            PROFILES,
            body,
            self.profile1,
            user='moderator',
            check_es=False,
        )

        assert profile.get_locale('es').description == 'Yo'
        search_doc = self._check_es_index(session)
        assert search_doc['title_es'] == 'Contributor contributor'

    def _check_es_index(self, session):
        sync_es(session)
        search_doc = SearchUser.get(
            id=self.profile1.document_id, index=elasticsearch_config['index']
        )
        assert search_doc['doc_type'] == self.profile1.type
        assert search_doc['title_en'] == 'Contributor contributor'
        assert search_doc['title_fr'] == 'Contributor contributor'
        return search_doc

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom') is not None

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        assert isinstance(point, Point)

    def _add_test_data(self, session, user_ids):
        user_id = user_ids['contributor']
        self.profile1 = session.get(UserProfile, user_id)
        self.locale_en = self.profile1.get_locale('en')
        self.locale_fr = self.profile1.get_locale('fr')

        self.profile2 = UserProfile(categories=['amateur'])
        session.add(self.profile2)
        self.profile3 = UserProfile(categories=['amateur'])
        session.add(self.profile3)
        self.profile4 = UserProfile(categories=['amateur'])
        self.profile4.locales.append(
            DocumentLocale(lang='en', description='You', title='')
        )
        self.profile4.locales.append(
            DocumentLocale(lang='fr', description='Toi', title='')
        )
        session.add(self.profile4)

        session.flush()

        # create users for the profiles
        self.user2 = User(
            name='user2',
            username='user2',
            email='user2@c2c.org',
            forum_username='user2',
            password='pass',
            email_validated=True,
            profile=self.profile2,
        )
        self.user3 = User(
            name='user3',
            username='user3',
            email='user3@c2c.org',
            forum_username='user3',
            password='pass',
            email_validated=False,
            profile=self.profile3,
        )
        self.user4 = User(
            name='user4',
            username='user4',
            email='user4@c2c.org',
            forum_username='user4',
            password='pass',
            email_validated=True,
            profile=self.profile4,
        )
        session.add_all([self.user2, self.user3, self.user4])

        session.flush()
