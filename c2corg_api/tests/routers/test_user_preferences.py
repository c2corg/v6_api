"""
Tests for the FastAPI user preferences router
(``/v2/users/preferences``).

Mirrors ``c2corg_api/tests/views/test_user_preferences.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import FilterArea
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class TestUserPreferencesFastAPIRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)

        self._prefix = '/v2/users/preferences'

        self.area1 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='France'),
                DocumentLocale(lang='de', title='Frankreich'),
            ],
        )
        self.area2 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='Suisse')]
        )
        self.session.add_all([self.area1, self.area2])
        self.session.flush()

        self.contributor = self.session.get(User, global_userids['contributor'])
        self.contributor.feed_filter_areas.append(self.area1)
        self.contributor.feed_filter_activities = ['hiking']
        self.contributor.feed_filter_langs = ['fr']
        self.session.flush()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def test_get_preferences_unauthenticated(self):
        r = self.client.get(self._prefix)
        assert r.status_code == 403

    def test_get_preferences(self):
        r = self.client.get(self._prefix, headers=self._auth_headers('contributor'))
        assert r.status_code == 200
        body = r.json()

        assert ['hiking'] == body['activities']
        assert ['fr'] == body['langs']
        assert False is body['followed_only']
        areas = body['areas']
        assert 1 == len(areas)
        assert self.area1.document_id == areas[0]['document_id']
        locale = areas[0]['locales'][0]
        # not related to the langs pref above:
        assert 'fr' == locale['lang']

    def test_get_preferences_lang(self):
        """Get the preferences with parameter ``pl``."""
        r = self.client.get(
            self._prefix + '?pl=de', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        areas = body['areas']
        locale = areas[0]['locales'][0]
        assert 'de' == locale['lang']

    def test_post_preferences_unauthenticated(self):
        r = self.client.post(self._prefix, json={})
        assert r.status_code == 403

    def test_post_preferences_invalid(self):
        request_body = {
            # missing 'followed_only'
            # wrong activity
            'activities': ['hiking', 'soccer'],
            # wrong lang
            'langs': ['fr', 'xx'],
            # wrong area entry
            'areas': [{'id': self.area2.document_id}],
        }

        r = self.client.post(
            self._prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        body = r.json()
        assert body.get('status') == 'error'
        errors = body.get('errors')

        assert self._get_error(errors, 'activities') is not None
        assert self._get_error(errors, 'langs') is not None
        assert self._get_error(errors, 'areas.0.document_id') is not None
        assert self._get_error(errors, 'followed_only') is not None

    def test_post_preferences(self):
        request_body = {
            'followed_only': True,
            'activities': ['hiking', 'skitouring'],
            'langs': ['fr', 'en'],
            'areas': [{'document_id': self.area2.document_id}],
        }

        r = self.client.post(
            self._prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        self.session.flush()
        self.session.expire_all()
        self.session.refresh(self.contributor)
        assert self.contributor.feed_followed_only
        assert ['hiking', 'skitouring'] == self.contributor.feed_filter_activities
        assert ['fr', 'en'] == self.contributor.feed_filter_langs

        assert (
            self.session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area1.document_id,
            )
            .first()
            is None
        )
        assert (
            self.session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area2.document_id,
            )
            .first()
            is not None
        )

    def _get_error(self, errors, name):
        for error in errors:
            if name == error.get('name'):
                return error
        return None
