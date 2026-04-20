"""
Tests for the FastAPI User Account router (``/v2/users/account``).

Mirrors ``c2corg_api/tests/views/test_user_account.py``.
"""

from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.user import configure_user_router
from c2corg_api.routers.user_account import configure_user_account_router
from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import (
    BaseTestCase,
    global_passwords,
    global_tokens,
    global_userids,
    settings,
)
from c2corg_api.tests.routers import get_real_app

forum_username_tests = {
    'a': 'Shorter than minimum length 3',
    'a' * 3: False,
    'a' * 26: 'Longer than maximum length 25',
    'a' * 25: False,
    'test/test': 'Contain invalid character(s)',
    'test.test-test_test': False,
    '-test': 'First character is invalid',
    'test.': 'Last character is invalid',
    'test__test': 'Contains consecutive special characters',
    'test.jpg': 'Ended by confusing suffix',
}


class TestUserAccountRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_user_router(settings)
        configure_user_account_router(settings)

        self.original_discourse_client = get_discourse_client(settings)
        self._prefix = '/v2/users'
        self.set_discourse_up()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.set_discourse_not_mocked()
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def set_discourse_client_mock(self, client):
        self.discourse_client = client
        set_discourse_client(client)

    def set_discourse_not_mocked(self):
        self.set_discourse_client_mock(self.original_discourse_client)

    def set_discourse_up(self):
        mock = Mock()
        mock.redirect_without_nonce = MagicMock(
            return_value='https://discourse_redirect'
        )
        mock.redirect = MagicMock()
        mock.sso_sync = MagicMock()
        mock.sync_sso = MagicMock()
        self.set_discourse_client_mock(mock)

    def set_discourse_down(self):
        mock = APIDiscourseClient(settings)
        mock.redirect_without_nonce = MagicMock(
            return_value='https://discourse_redirect', side_effect=Exception
        )
        mock.redirect = MagicMock(side_effect=Exception)
        mock.sso_sync = MagicMock(side_effect=Exception)
        mock.sync_sso = MagicMock(side_effect=Exception)
        self.set_discourse_client_mock(mock)

    def _extract_nonce(self, _send_email, key):
        import re
        from urllib.parse import urlparse

        body_text = _send_email.call_args_list[0][1]['body']
        urls = re.findall(
            r'http[s]?://'
            r'(?:'
            r'[a-zA-Z]|[0-9]|[$-_@#.&+]|'
            r'[!*\(\),]|'
            r'(?:%[0-9a-fA-F][0-9a-fA-F])'
            r')+[0-9a-zA-Z]',
            body_text,
        )
        validation_url = urls[0]
        fragment = urlparse(validation_url).fragment
        nonce = fragment.replace(key + '=', '')
        return nonce

    # ── GET account ──────────────────────────────────────────

    def test_read_account_info(self):
        r = self.client.get(
            self._prefix + '/account', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()
        assert body['name'] == 'Contributor'
        assert body['email'] == 'contributor@camptocamp.org'
        assert body['forum_username'] == 'contributor'
        assert body['is_profile_public'] == False

    def test_read_account_info_blocked_account(self):
        contributor = self.session.get(User, global_userids['contributor'])
        contributor.blocked = True
        self.session.flush()

        r = self.client.get(
            self._prefix + '/account', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    # ── POST account (update) ────────────────────────────────

    def _update_field_discourse_up(self, field, value):
        currentpassword = global_passwords['contributor']
        data = {'currentpassword': currentpassword}
        data[field] = value
        r = self.client.post(
            self._prefix + '/account',
            json=data,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200

    def _update_field_discourse_down(self, field, value):
        self.set_discourse_down()
        currentpassword = global_passwords['contributor']
        data = {'currentpassword': currentpassword}
        data[field] = value
        r = self.client.post(
            self._prefix + '/account',
            json=data,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 500

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_update_account_email_discourse_up(self, _send_email):
        new_email = 'superemail@localhost.localhost'
        self._update_field_discourse_up('email', new_email)

        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.email_to_validate == new_email
        assert user.email != new_email

        _send_email.assert_called_once()

        # Simulate email validation
        nonce = self._extract_nonce(_send_email, 'validate_change_email')
        r = self.client.post(self._prefix + '/validate_change_email/' + nonce, json={})
        assert r.status_code == 200

        self.session.expunge(user)
        user = self.session.get(User, user_id)
        assert user.email == new_email
        assert user.validation_nonce is None

    def test_update_account_email_discourse_down(self):
        new_email = 'superemail@localhost.localhost'
        self._update_field_discourse_down('email', new_email)

    def test_update_account_name_discourse_up(self):
        self._update_field_discourse_up('name', 'changed')

        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.name == 'changed'

    def test_update_account_name_discourse_down(self):
        self._update_field_discourse_down('name', 'changed')

    def test_update_account_forum_username_validity(self):
        i = 0
        for forum_username, value in forum_username_tests.items():
            i += 1
            data = {
                'currentpassword': global_passwords['contributor'],
                'forum_username': forum_username,
            }
            r = self.client.post(
                self._prefix + '/account',
                json=data,
                headers=self._auth_headers('contributor'),
            )
            if value is False:
                assert r.status_code == 200, f'{forum_username}'
            else:
                assert r.status_code == 400, f'{forum_username}'
                body = r.json()
                errors = body['errors']
                assert any(e['description'] == value for e in errors), (
                    f'Expected "{value}" for "{forum_username}"'
                )

    def test_update_account_forum_username_unique(self):
        data = {
            'currentpassword': global_passwords['contributor'],
            'forum_username': 'unique',
        }
        r = self.client.post(
            self._prefix + '/account',
            json=data,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200

        data2 = {
            'currentpassword': global_passwords['contributor2'],
            'forum_username': 'Unique',
        }
        r2 = self.client.post(
            self._prefix + '/account',
            json=data2,
            headers=self._auth_headers('contributor2'),
        )
        assert r2.status_code == 400
        body = r2.json()
        errors = body['errors']
        assert any('Already used forum name' in e['description'] for e in errors)

    def test_update_account_forum_username_discourse_up(self):
        self._update_field_discourse_up('forum_username', 'changed')

        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.forum_username == 'changed'

    def test_update_account_forum_username_discourse_down(self):
        self._update_field_discourse_down('forum_username', 'changed')

    def test_update_is_profile_public(self):
        data = {
            'currentpassword': global_passwords['contributor'],
            'is_profile_public': True,
        }
        r = self.client.post(
            self._prefix + '/account',
            json=data,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200

        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.is_profile_public == True

    def test_update_is_profile_public_discourse_down(self):
        # is_profile_public does not require a Discourse sync, so it succeeds
        # even when Discourse is unavailable.
        self.set_discourse_down()
        data = {
            'currentpassword': global_passwords['contributor'],
            'is_profile_public': True,
        }
        r = self.client.post(
            self._prefix + '/account',
            json=data,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200

        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.is_profile_public == True

    def test_update_preferred_lang(self):
        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user.lang == 'fr'

        r = self.client.post(
            self._prefix + '/update_preferred_language',
            json={'lang': 'en'},
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200

        self.session.expunge(user)
        user = self.session.get(User, user_id)
        assert user.lang == 'en'
