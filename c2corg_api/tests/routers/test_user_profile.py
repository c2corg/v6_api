"""
Tests for the FastAPI user profile router (``/v2/profiles``).

Mirrors ``c2corg_api/tests/views/test_user_profile.py`` — same test data,
same assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.
"""

import json

from fastapi.testclient import TestClient
from shapely.geometry import Point, shape

from c2corg_api.database import get_db
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class TestUserProfileFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/profiles``.

    Mirrors ``TestUserProfileRest`` from ``tests/views/test_user_profile.py``.
    """

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────────────
    # Test data setup (mirrors TestUserProfileRest._add_test_data)
    # ──────────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']
        self.profile1 = self.session.get(UserProfile, user_id)
        self.locale_en = self.profile1.get_locale('en')
        self.locale_fr = self.profile1.get_locale('fr')
        create_new_version(self.profile1, user_id, db=self.session)

        self.profile2 = UserProfile(categories=['amateur'])
        self.session.add(self.profile2)
        self.profile3 = UserProfile(categories=['amateur'])
        self.session.add(self.profile3)
        self.profile4 = UserProfile(categories=['amateur'])
        self.profile4.locales.append(
            DocumentLocale(lang='en', description='You', title='')
        )
        self.profile4.locales.append(
            DocumentLocale(lang='fr', description='Toi', title='')
        )
        self.session.add(self.profile4)

        self.session.flush()

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
        self.session.add_all([self.user2, self.user3, self.user4])

        self.session.flush()

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom') is not None

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        assert isinstance(point, Point)

    # ──────────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────────

    def test_get_collection_unauthenticated(self):
        resp = self.client.get('/v2/profiles')
        assert resp.status_code == 403, resp.text

    def test_get_collection(self):
        resp = self.client.get(
            '/v2/profiles', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'documents' in body
        doc = body['documents'][0]
        assert 'name' in doc
        assert 'username' not in doc

    def test_get_collection_paginated(self):
        resp = self.client.get(
            '/v2/profiles?offset=0&limit=0', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['total'] == 8
        assert len(body['documents']) == 0

        resp = self.client.get(
            '/v2/profiles?offset=0&limit=1', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['total'] == 8
        assert len(body['documents']) == 1
        assert body['documents'][0]['document_id'] == self.profile4.document_id

    def test_get_collection_lang(self):
        resp = self.client.get(
            '/v2/profiles?pl=en', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for doc in body['documents']:
            if doc.get('locales'):
                locale = doc['locales'][0]
                assert locale['lang'] == 'en'

    # ──────────────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────────────

    def test_get_unauthenticated_private_profile(self):
        """Only the user name is returned for a private profile when
        unauthenticated.
        """
        resp = self.client.get(f'/v2/profiles/{self.profile1.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body.get('not_authorized') == True
        assert 'username' not in body
        assert 'name' in body
        assert 'locales' not in body
        assert 'geometry' not in body

    def test_get_unauthenticated_public_profile(self):
        """Full profile is returned for a public profile even when
        unauthenticated.
        """
        contributor = self.profile1.user
        contributor.is_profile_public = True
        self.session.flush()

        resp = self.client.get(f'/v2/profiles/{self.profile1.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert 'username' not in body
        assert 'name' in body
        assert 'locales' in body
        assert 'geometry' in body

    def test_get(self):
        resp = self.client.get(
            f'/v2/profiles/{self.profile1.document_id}',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        self._assert_geometry(body)
        assert 'title' not in body['locales'][0]
        assert 'maps' not in body
        assert 'username' not in body
        assert 'name' in body
        assert 'forum_username' in body

    def test_get_unconfirmed_user(self):
        resp = self.client.get(
            f'/v2/profiles/{self.profile3.document_id}',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 404, resp.text

    def test_get_404(self):
        resp = self.client.get(
            '/v2/profiles/9999999', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 404, resp.text

    def test_get_cooked(self):
        resp = self.client.get(
            f'/v2/profiles/{self.profile1.document_id}?cook=en',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(
            f'/v2/profiles/{self.profile1.document_id}?cook=it',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_lang(self):
        resp = self.client.get(
            f'/v2/profiles/{self.profile1.document_id}?l=en',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body['locales']) == 1
        assert body['locales'][0]['lang'] == 'en'

    def test_get_new_lang(self):
        """Request a language not yet translated for this document."""
        resp = self.client.get(
            f'/v2/profiles/{self.profile1.document_id}?l=it',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['locales'] == []

    # ──────────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/profiles/{self.profile1.document_id}/en/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locale = body.get('locales')[0]
        assert locale.get('lang') == 'en'
        assert locale.get('title') == 'Contributor'

    def test_get_info_404(self):
        resp = self.client.get('/v2/profiles/9999999/en/info')
        assert resp.status_code == 404, resp.text

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/profiles/{self.profile1.document_id}/it/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locale = body.get('locales')[0]
        assert locale.get('lang') in ['en', 'fr']

    # ──────────────────────────────────────────────────────────────────
    # POST — user profiles cannot be created via API
    # ──────────────────────────────────────────────────────────────────

    def test_no_post(self):
        resp = self.client.post(
            '/v2/profiles', json={}, headers=self._auth_headers('contributor')
        )
        # FastAPI returns 405 Method Not Allowed for undefined POST
        assert resp.status_code in [404, 405]

    # ──────────────────────────────────────────────────────────────────
    # PUT
    # ──────────────────────────────────────────────────────────────────

    def test_put_wrong_user(self):
        """A normal user can only edit their own profile."""
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
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 403, resp.text

    def test_put_wrong_document_id(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': 9999999,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'Me!',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400, resp.text

    def test_put_wrong_document_version(self):
        body = {
            'message': 'Update',
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
            },
        }
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_locale_version(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'categories': ['mountain_guide'],
                'locales': [{'lang': 'en', 'description': 'Me!', 'version': -9999}],
            },
        }
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_ids(self):
        """URL id != body document_id → 400."""
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
            },
        }
        resp = self.client.put(
            f'/v2/profiles/{self.profile2.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400, resp.text

    def test_put_no_document(self):
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json={},
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code in [400, 422]

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': QualityTypes.draft,
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
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        # Check that the changes were applied
        self.session.refresh(self.profile1)
        assert self.profile1.categories == ['mountain_guide']
        assert self.profile1.get_locale('en').description == 'Me!'

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': QualityTypes.draft,
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
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.refresh(self.profile1)
        assert self.profile1.categories == ['mountain_guide']

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': QualityTypes.draft,
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
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.refresh(self.profile1)
        assert self.profile1.get_locale('en').description == 'Me!'

    def test_put_reset_title(self):
        """The title cannot be set — it is silently reset to ''."""
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': QualityTypes.draft,
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
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.refresh(self.profile1)
        assert self.profile1.get_locale('en').description == 'Me!'
        self.session.refresh(self.locale_en)
        assert self.locale_en.title == ''

    def test_put_success_new_lang(self):
        """Update a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.profile1.document_id,
                'version': self.profile1.version,
                'quality': QualityTypes.draft,
                'categories': ['amateur'],
                'locales': [{'lang': 'es', 'description': 'Yo'}],
            },
        }
        resp = self.client.put(
            f'/v2/profiles/{self.profile1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.refresh(self.profile1)
        assert self.profile1.get_locale('es').description == 'Yo'
