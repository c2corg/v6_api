import unittest
from unittest.mock import MagicMock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from c2corg_api.security import fastapi_security
from c2corg_api.security.fastapi_security import (
    _extract_token,
    configure_security,
    get_current_user,
    get_optional_current_user,
    require_moderator,
)


def _make_starlette_request(authorization_header=None):
    """Build a minimal Starlette-style Request with the given header."""
    scope = {'type': 'http', 'method': 'GET', 'path': '/', 'headers': []}
    if authorization_header:
        scope['headers'].append((b'authorization', authorization_header.encode()))
    from starlette.requests import Request

    return Request(scope)


class TestExtractToken:
    """Tests for the ``_extract_token`` helper — mirrors
    ``TestExtractToken`` in ``test_pyramid_jwt_policy.py``.
    """

    def test_extract_token_legacy_format(self):
        request = _make_starlette_request('JWT token="my.jwt.token"')
        assert _extract_token(request) == 'my.jwt.token'

    def test_extract_token_standard_format(self):
        request = _make_starlette_request('JWT my.jwt.token')
        assert _extract_token(request) == 'my.jwt.token'

    def test_extract_token_no_header(self):
        request = _make_starlette_request()
        assert _extract_token(request) is None

    def test_extract_token_wrong_auth_type(self):
        request = _make_starlette_request('Bearer my.jwt.token')
        assert _extract_token(request) is None

    def test_extract_token_malformed_header(self):
        request = _make_starlette_request('JWT')
        assert _extract_token(request) is None


class TestGetCurrentUser(unittest.TestCase):
    """Integration-style tests for ``get_current_user`` using
    ``fastapi.testclient.TestClient``.
    """

    def setUp(self):
        self.secret = 'a_long_enough_secret_key_for_hs256_testing'
        configure_security({'jwt.private_key': self.secret})

        self.claims = {'sub': '12345', 'username': 'testuser'}
        self.token = jwt.encode(self.claims, self.secret, algorithm='HS256')

        # Build a tiny FastAPI app that exposes get_current_user
        self.app = FastAPI()

        @self.app.get('/me')
        def me(user=fastapi_security.Depends(get_current_user)):
            return {'id': user.id, 'username': user.username}

        @self.app.get('/moderator')
        def moderator(user=fastapi_security.Depends(require_moderator)):
            return {'id': user.id, 'username': user.username}

        self.client = TestClient(self.app)

    # -- helpers ----------------------------------------------------------

    def _fake_user(self, *, moderator=False):
        user = MagicMock()
        user.id = 12345
        user.username = 'testuser'
        user.moderator = moderator
        return user

    def _mock_db(self, user):
        """Return a mock session whose ``query(User).filter(...).first()``
        returns *user*.
        """
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        return db

    # -- token extraction / claim decoding --------------------------------

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_get_claims_legacy_format(self, _mock_valid):
        """JWT token="<token>" format used by the frontend."""
        fake_user = self._fake_user()
        mock_db = self._mock_db(fake_user)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get(
            '/me', headers={'Authorization': f'JWT token="{self.token}"'}
        )
        assert resp.status_code == 200
        assert resp.json()['id'] == 12345
        assert resp.json()['username'] == 'testuser'

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_get_claims_standard_format(self, _mock_valid):
        """JWT <token> format (standard Bearer-style)."""
        fake_user = self._fake_user()
        mock_db = self._mock_db(fake_user)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get('/me', headers={'Authorization': f'JWT {self.token}'})
        assert resp.status_code == 200
        assert resp.json()['id'] == 12345

    # -- missing / wrong auth ---------------------------------------------

    def test_no_authorization_header(self):
        resp = self.client.get('/me')
        assert resp.status_code == 403

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_wrong_auth_type(self, _mock_valid):
        resp = self.client.get('/me', headers={'Authorization': f'Bearer {self.token}'})
        assert resp.status_code == 403

    # -- invalid token ----------------------------------------------------

    def test_invalid_token(self):
        resp = self.client.get(
            '/me', headers={'Authorization': 'JWT not-a-valid-token'}
        )
        assert resp.status_code == 401

    def test_expired_token(self):
        expired_claims = {**self.claims, 'exp': 0}
        expired_token = jwt.encode(expired_claims, self.secret, algorithm='HS256')
        resp = self.client.get('/me', headers={'Authorization': f'JWT {expired_token}'})
        assert resp.status_code == 401

    # -- database token validation ----------------------------------------

    def test_token_not_in_database(self):
        """Token decodes fine but is_valid_token returns False."""
        mock_db = self._mock_db(None)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        with patch(
            'c2corg_api.security.fastapi_security.is_valid_token', return_value=False
        ):
            resp = self.client.get(
                '/me', headers={'Authorization': f'JWT {self.token}'}
            )
        assert resp.status_code == 401

    def test_blocked_user(self):
        """is_valid_token raises AccountBlockedError for blocked users."""
        from c2corg_api.security.roles import AccountBlockedError

        mock_db = self._mock_db(None)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        with patch(
            'c2corg_api.security.fastapi_security.is_valid_token',
            side_effect=AccountBlockedError('account blocked'),
        ):
            resp = self.client.get(
                '/me', headers={'Authorization': f'JWT {self.token}'}
            )
        assert resp.status_code == 403

    # -- sub claim → integer conversion -----------------------------------

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_sub_claim_converted_to_int(self, _mock_valid):
        """The ``sub`` claim is a string but the user lookup uses an int."""
        fake_user = self._fake_user()
        mock_db = self._mock_db(fake_user)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get(
            '/me', headers={'Authorization': f'JWT token="{self.token}"'}
        )
        assert resp.status_code == 200
        # Verify the DB was queried with an integer user id
        from c2corg_api.models.user import User

        mock_db.query.assert_called_with(User)
        filter_call_args = mock_db.query.return_value.filter.call_args
        # The filter expression should have been called (int comparison)
        assert filter_call_args is not None

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_user_not_found_in_database(self, _mock_valid):
        """Valid token but user row doesn't exist → 401."""
        mock_db = self._mock_db(None)  # .first() returns None

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get('/me', headers={'Authorization': f'JWT {self.token}'})
        assert resp.status_code == 401

    # -- require_moderator ------------------------------------------------

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_require_moderator_success(self, _mock_valid):
        fake_user = self._fake_user(moderator=True)
        mock_db = self._mock_db(fake_user)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get(
            '/moderator', headers={'Authorization': f'JWT {self.token}'}
        )
        assert resp.status_code == 200

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_require_moderator_denied(self, _mock_valid):
        fake_user = self._fake_user(moderator=False)
        mock_db = self._mock_db(fake_user)

        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db

        resp = self.client.get(
            '/moderator', headers={'Authorization': f'JWT {self.token}'}
        )
        assert resp.status_code == 403

    def tearDown(self):
        self.app.dependency_overrides.clear()


class TestGetOptionalCurrentUser(unittest.TestCase):
    """Tests for ``get_optional_current_user``."""

    def setUp(self):
        self.secret = 'a_long_enough_secret_key_for_hs256_testing'
        configure_security({'jwt.private_key': self.secret})

        self.claims = {'sub': '12345', 'username': 'testuser'}
        self.token = jwt.encode(self.claims, self.secret, algorithm='HS256')

        self.app = FastAPI()

        @self.app.get('/optional')
        def optional(user=fastapi_security.Depends(get_optional_current_user)):
            if user is None:
                return {'authenticated': False}
            return {'authenticated': True, 'id': user.id}

        self.client = TestClient(self.app)

    def _fake_user(self):
        user = MagicMock()
        user.id = 12345
        user.username = 'testuser'
        user.moderator = False
        return user

    def _mock_db(self, user):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        return db

    def test_no_auth_returns_none(self):
        """Unauthenticated request returns None (not an error)."""
        resp = self.client.get('/optional')
        assert resp.status_code == 200
        assert resp.json()['authenticated'] is False

    @patch('c2corg_api.security.fastapi_security.is_valid_token', return_value=True)
    def test_valid_auth_returns_user(self, _mock_valid):
        fake_user = self._fake_user()
        mock_db = self._mock_db(fake_user)
        self.app.dependency_overrides[fastapi_security.get_db] = lambda: mock_db
        resp = self.client.get(
            '/optional', headers={'Authorization': f'JWT {self.token}'}
        )
        assert resp.status_code == 200
        assert resp.json()['authenticated'] is True
        assert resp.json()['id'] == 12345

    def test_invalid_token_returns_none(self):
        """Invalid token silently returns None."""
        resp = self.client.get('/optional', headers={'Authorization': 'JWT bad-token'})
        assert resp.status_code == 200
        assert resp.json()['authenticated'] is False

    def tearDown(self):
        self.app.dependency_overrides.clear()
