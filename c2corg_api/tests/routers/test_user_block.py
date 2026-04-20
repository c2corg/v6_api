"""
Tests for the FastAPI User Block router (``/v2/users/block``).

Mirrors ``c2corg_api/tests/views/test_user_block.py``.
"""

from unittest.mock import MagicMock, Mock

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.user_block import configure_user_block_router
from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class BaseBlockTestRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_user_block_router(settings)

        self.original_discourse_client = get_discourse_client(settings)

        self.contributor = self.session.get(User, global_userids['contributor'])
        self.contributor2 = self.session.get(User, global_userids['contributor2'])
        self.moderator = self.session.get(User, global_userids['moderator'])
        assert self.contributor is not None
        assert self.contributor2 is not None
        assert self.moderator is not None

        self.contributor2.blocked = True
        self.contributor2.ratelimit_times = 2
        self.session.flush()

        self.set_discourse_up()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        set_discourse_client(self.original_discourse_client)
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def set_discourse_client_mock(self, client):
        self.discourse_client = client
        set_discourse_client(client)

    def set_discourse_up(self):
        mock = Mock()
        mock.get_userid = MagicMock()
        mock.suspend = MagicMock()
        mock.unsuspend = MagicMock()
        self.set_discourse_client_mock(mock)

    def set_discourse_down(self):
        mock = APIDiscourseClient(settings)
        mock.get_userid = MagicMock(side_effect=Exception)
        mock.suspend = MagicMock(side_effect=Exception)
        mock.unsuspend = MagicMock(side_effect=Exception)
        self.set_discourse_client_mock(mock)

    def is_blocked(self, user_id):
        user = self.session.get(User, user_id)
        assert user is not None
        return user.blocked


class TestUserBlockRouter(BaseBlockTestRouter):
    def test_block_unauthorized(self):
        r = self.client.post('/v2/users/block', json={}, headers={})
        assert r.status_code == 403

        r2 = self.client.post(
            '/v2/users/block', json={}, headers=self._auth_headers('contributor')
        )
        assert r2.status_code == 403

    def test_block(self):
        assert self.contributor is not None
        body = {'user_id': self.contributor.id}
        r = self.client.post(
            '/v2/users/block', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        assert self.is_blocked(self.contributor.id)

    def test_block_already_blocked_user(self):
        assert self.contributor is not None
        body = {'user_id': self.contributor.id}
        headers = self._auth_headers('moderator')
        self.client.post('/v2/users/block', json=body, headers=headers)
        r = self.client.post('/v2/users/block', json=body, headers=headers)
        assert r.status_code == 200
        assert self.is_blocked(self.contributor.id)

    def test_block_discourse_error(self):
        assert self.contributor is not None
        self.set_discourse_down()
        body = {'user_id': self.contributor.id}
        r = self.client.post(
            '/v2/users/block', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 500
        assert not self.is_blocked(self.contributor.id)

    def test_block_invalid_user_id(self):
        body = {'user_id': -1}
        r = self.client.post(
            '/v2/users/block', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('user_id' in e.get('name', '') for e in errors)


class TestUserUnblockRouter(BaseBlockTestRouter):
    def test_unblock_unauthorized(self):
        r = self.client.post('/v2/users/unblock', json={}, headers={})
        assert r.status_code == 403

        r2 = self.client.post(
            '/v2/users/unblock', json={}, headers=self._auth_headers('contributor')
        )
        assert r2.status_code == 403

    def test_unblock(self):
        assert self.contributor2 is not None
        body = {'user_id': self.contributor2.id}
        assert self.is_blocked(self.contributor2.id)
        assert self.contributor2.ratelimit_times != 0

        r = self.client.post(
            '/v2/users/unblock', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        assert not self.is_blocked(self.contributor2.id)
        assert self.contributor2.ratelimit_times == 0

    def test_unblock_not_blocked_user(self):
        assert self.contributor is not None
        body = {'user_id': self.contributor.id}
        r = self.client.post(
            '/v2/users/unblock', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        assert not self.is_blocked(self.contributor.id)

    def test_unblock_invalid_user_id(self):
        body = {'user_id': -1}
        r = self.client.post(
            '/v2/users/unblock', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('user_id' in e.get('name', '') for e in errors)

    def test_unblock_discourse_error(self):
        assert self.contributor2 is not None
        self.set_discourse_down()
        body = {'user_id': self.contributor2.id}
        assert self.is_blocked(self.contributor2.id)

        r = self.client.post(
            '/v2/users/unblock', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 500
        assert self.is_blocked(self.contributor2.id)


class TestUserBlockedRouter(BaseBlockTestRouter):
    def test_blocked_unauthorized(self):
        r = self.client.get('/v2/users/blocked/123')
        assert r.status_code == 403

        r2 = self.client.get(
            '/v2/users/blocked', headers=self._auth_headers('contributor')
        )
        assert r2.status_code == 403

    def test_blocked(self):
        assert self.contributor2 is not None
        r = self.client.get(
            '/v2/users/blocked/{}'.format(self.contributor2.id),
            headers=self._auth_headers('moderator'),
        )
        assert r.status_code == 200
        assert r.json()['blocked']

    def test_blocked_not(self):
        assert self.contributor is not None
        r = self.client.get(
            '/v2/users/blocked/{}'.format(self.contributor.id),
            headers=self._auth_headers('moderator'),
        )
        assert r.status_code == 200
        assert not r.json()['blocked']

    def test_blocked_wrong_user_id(self):
        r = self.client.get(
            '/v2/users/blocked/9999999999', headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400

    def test_blocked_invalid_user_id(self):
        # Non-integer path param; FastAPI returns 422 (Pyramid returned 400)
        r = self.client.get(
            '/v2/users/blocked/invalid-user-id', headers=self._auth_headers('moderator')
        )
        assert r.status_code in (400, 422)


class TestUserBlockedAllRouter(BaseBlockTestRouter):
    def test_blocked_unauthenticated(self):
        r = self.client.get('/v2/users/blocked')
        assert r.status_code == 403

        r2 = self.client.get(
            '/v2/users/blocked', headers=self._auth_headers('contributor')
        )
        assert r2.status_code == 403

    def test_blocked(self):
        assert self.contributor2 is not None
        r = self.client.get(
            '/v2/users/blocked', headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        body = r.json()
        blocked_users = body['blocked']
        assert 1 == len(blocked_users)
        assert self.contributor2.id == blocked_users[0]['document_id']
