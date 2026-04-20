"""
Tests for the FastAPI User router (``/v2/users/...``).

Mirrors ``c2corg_api/tests/views/test_user.py``.
"""

import re
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.routers.user import configure_user_router
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


class BaseUserTestRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_user_router(settings)

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
        self.set_discourse_client_mock(mock)

    def set_discourse_down(self):
        mock = APIDiscourseClient(settings)
        mock.redirect_without_nonce = MagicMock(
            return_value='https://discourse_redirect', side_effect=Exception
        )
        mock.redirect = MagicMock(side_effect=Exception)
        mock.sso_sync = MagicMock(side_effect=Exception)
        self.set_discourse_client_mock(mock)

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def extract_urls(self, data):
        return re.findall(
            r'http[s]?://'
            r'(?:'
            r'[a-zA-Z]|'
            r'[0-9]|'
            r'[$-_@#.&+]|'
            r'[!*\(\),]|'
            r'(?:%[0-9a-fA-F][0-9a-fA-F])'
            r')+[0-9a-zA-Z]',
            data,
        )

    def extract_nonce(self, _send_mail, key):
        match = self.extract_urls(_send_mail.call_args_list[0][1]['body'])
        validation_url = match[0]
        fragment = urlparse(validation_url).fragment
        nonce = fragment.replace(key + '=', '')
        return nonce


class TestUserRouterRegister(BaseUserTestRouter):
    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_default_lang(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'test',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        data = r.json()
        user = self.session.get(User, data['id'])
        assert user.lang == 'fr'

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_passed_lang(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'test',
            'lang': 'en',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        data = r.json()
        user = self.session.get(User, data['id'])
        assert user.lang == 'en'

    def test_register_invalid_lang(self):
        body = {
            'username': 'test',
            'forum_username': 'test',
            'lang': 'nn',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_non_validated_users(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'test',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email_validated': True,
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        data = r.json()
        user = self.session.get(User, data['id'])
        assert not user.email_validated
        assert user.tos_validated is not None

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_forum_username_validity(self, _send_email):
        i = 0
        for forum_username, value in forum_username_tests.items():
            i += 1
            body = {
                'username': 'test{}'.format(i),
                'forum_username': forum_username,
                'name': 'Max Mustermann{}'.format(i),
                'password': 'super secret',
                'email': 'some_user{}@camptocamp.org'.format(i),
            }
            r = self.client.post(self._prefix + '/register', json=body)
            if value is False:
                assert r.status_code == 200, f'{forum_username}'
            else:
                assert r.status_code == 400, f'{forum_username}'
                data = r.json()
                errors = data['errors']
                assert any(e['description'] == value for e in errors), (
                    f'Expected error "{value}" for "{forum_username}"'
                )

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_forum_username_unique(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'Contributor',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('already used forum_username' in e['description'] for e in errors)

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_discourse_up(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        data = r.json()
        assert data['username'] == 'test'
        assert data['forum_username'] == 'testf'
        assert data['name'] == 'Max Mustermann'
        assert data['email'] == 'some_user@camptocamp.org'
        assert 'password' not in data
        assert 'id' in data

        user_id = data['id']
        user = self.session.get(User, user_id)
        assert user is not None
        assert not user.email_validated
        profile = self.session.get(UserProfile, user_id)
        assert profile is not None

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_duplicate_email(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        # First registration
        self.client.post(self._prefix + '/register', json=body)
        # Second with same email
        body['username'] = 'test2'
        body['forum_username'] = 'testf2'
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('email' in e.get('name', '') for e in errors)


class TestUserRouterLogin(BaseUserTestRouter):
    def _login(
        self,
        username,
        password=None,
        accept_tos=None,
        discourse=None,
        sso=None,
        sig=None,
    ):
        if not password:
            password = global_passwords[username]
        body = {'username': username, 'password': password}
        if accept_tos is not None:
            body['accept_tos'] = accept_tos
        if discourse is not None:
            body['discourse'] = discourse
        if sso is not None:
            body['sso'] = sso
        if sig is not None:
            body['sig'] = sig
        return self.client.post(self._prefix + '/login', json=body)

    def test_login_success(self):
        r = self._login('moderator')
        assert r.status_code == 200
        data = r.json()
        assert 'token' in data

    def test_login_success_use_email(self):
        r = self._login('moderator@camptocamp.org', global_passwords['moderator'])
        assert r.status_code == 200
        data = r.json()
        assert 'token' in data

    def test_login_blocked_account(self):
        contributor = self.session.get(User, global_userids['contributor'])
        contributor.blocked = True
        self.session.flush()

        r = self._login('contributor')
        assert r.status_code == 403

    def test_login_failure(self):
        r = self._login('moderator', password='invalid')
        assert r.status_code == 401
        data = r.json()
        errors = data['errors']
        assert any(e['description'] == 'Login failed' for e in errors)

    def test_login_no_tos_failure(self):
        r = self._login('contributornotos', password='some pass')
        assert r.status_code == 403

    def test_login_no_tos_success(self):
        r = self._login('contributornotos', password='some pass', accept_tos=True)
        assert r.status_code == 200
        data = r.json()
        assert 'token' in data

    def test_login_logout(self):
        r = self._login('moderator')
        assert r.status_code == 200
        data = r.json()
        token = data['token']

        headers = {'Authorization': f'JWT token="{token}"'}
        r2 = self.client.post(self._prefix + '/logout', json={}, headers=headers)
        assert r2.status_code == 200

    def test_renew_success(self):
        token = global_tokens['contributor']
        headers = {'Authorization': f'JWT token="{token}"'}
        r = self.client.post(self._prefix + '/renew', headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert 'expire' in data


class TestUserRouterPasswordChange(BaseUserTestRouter):
    def test_forgot_password_non_existing_email(self):
        r = self.client.post(
            self._prefix + '/request_password_change',
            json={'email': 'non_existing@camptocamp.org'},
        )
        assert r.status_code == 400

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_forgot_password_discourse_up(self, _send_email):
        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        initial_password = user.password

        r = self.client.post(
            self._prefix + '/request_password_change', json={'email': user.email}
        )
        assert r.status_code == 200

        nonce = self.extract_nonce(_send_email, 'change_password')
        r2 = self.client.post(
            self._prefix + '/validate_new_password/' + nonce,
            json={'password': 'new pass'},
        )
        assert r2.status_code == 200

        self.session.expunge(user)
        user = self.session.get(User, user_id)
        assert user.validation_nonce is None
        assert user.password != initial_password

    def test_forgot_password_blocked_account(self):
        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        user.blocked = True
        self.session.flush()

        r = self.client.post(
            self._prefix + '/request_password_change', json={'email': user.email}
        )
        assert r.status_code == 403


class TestUserRouterEmailValidation(BaseUserTestRouter):
    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_and_validate_email(self, _send_email):
        body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        user_id = r.json()['id']

        nonce = self.extract_nonce(_send_email, 'validate_register_email')
        r2 = self.client.post(
            self._prefix + '/validate_register_email/' + nonce, json={}
        )
        assert r2.status_code == 200

        user = self.session.get(User, user_id)
        self.session.refresh(user)
        assert user.email_validated

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_discourse_down(self, _send_email):
        self.set_discourse_down()
        body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        # Registration itself should succeed
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200

        nonce = self.extract_nonce(_send_email, 'validate_register_email')
        # Validation should fail because discourse is down
        r2 = self.client.post(
            self._prefix + '/validate_register_email/' + nonce, json={}
        )
        assert r2.status_code == 500

    def test_validate_invalid_nonce(self):
        r = self.client.post(self._prefix + '/validate_register_email/invalid', json={})
        assert r.status_code == 400


class TestUserRouterRegisterExtra(BaseUserTestRouter):
    """Additional register tests mirroring view tests not yet in the router suite."""

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_always_register_non_validated_users(self, _send_email):
        """Passing email_validated=True in the body is silently ignored;
        the user is always created un-validated."""
        body = {
            'username': 'test',
            'forum_username': 'test',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email_validated': True,
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200
        user = self.session.get(User, r.json()['id'])
        assert user is not None
        assert not user.email_validated
        assert user.tos_validated is not None

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_invalid_email(self, _send_email):
        """A malformed email address must be rejected with an informative error."""
        body = {
            'username': 'test',
            'forum_username': 'Contributor4',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_useratcamptocamp.org',  # missing @
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        descriptions = ' '.join(e.get('description', '') for e in errors).lower()
        assert 'email' in descriptions

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_stripped_username(self, _send_email):
        """Usernames with surrounding spaces are stripped before the uniqueness
        check; a duplicate is detected and a new unique username is accepted."""
        # Stripped ' contributor ' equals existing username → conflict
        body = {
            'username': ' contributor ',
            'forum_username': 'Foo',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('already exists' in e.get('description', '') for e in errors)

        # Stripped ' username with spaces ' is unique → ok
        body2 = {
            'username': ' username with spaces ',
            'forum_username': 'Spaceman',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'space@camptocamp.org',
        }
        r2 = self.client.post(self._prefix + '/register', json=body2)
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2['username'] == 'username with spaces'
        user = self.session.get(User, data2['id'])
        assert user is not None
        assert user.username == 'username with spaces'

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_username_email_not_equals_email(self, _send_email):
        """If the username looks like an email it must match the account email."""
        body = {
            'username': 'someone_else@camptocamp.org',
            'forum_username': 'Contributor4',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        descriptions = ' '.join(e.get('description', '') for e in errors)
        assert 'same' in descriptions

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_username_email_equals_email(self, _send_email):
        """A username that is an email address is accepted when it matches
        the account email."""
        body = {
            'username': 'some_user@camptocamp.org',
            'forum_username': 'Contributor4',
            'name': 'Frankie Vincent',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200


class TestUserRouterLoginExtra(BaseUserTestRouter):
    """Additional login tests mirroring view tests not yet in the router suite."""

    def _login(self, username, password=None, discourse=False, sso=None, sig=None):
        if password is None:
            password = global_passwords[username]
        body = {'username': username, 'password': password}
        if discourse:
            body['discourse'] = True
        if sso:
            body['sso'] = sso
        if sig:
            body['sig'] = sig
        return self.client.post(self._prefix + '/login', json=body)

    def test_login_success_discourse_up(self):
        """Login with Discourse mock up returns a token."""
        r = self._login('moderator')
        assert r.status_code == 200
        assert 'token' in r.json()

    def test_login_success_discourse_down(self):
        """Login still works when Discourse is down (token-only path)."""
        self.set_discourse_down()
        r = self._login('moderator')
        assert r.status_code == 200
        assert 'token' in r.json()

    def test_login_logout_success(self):
        """Full login → check expire field → logout cycle."""
        import time

        r = self._login('moderator')
        assert r.status_code == 200
        data = r.json()
        assert 'token' in data
        assert 'expire' in data
        # expire should be ~14 days from now
        now = int(round(time.time()))
        expected = 14 * 24 * 3600 + now
        assert abs(data['expire'] - expected) < 10

        headers = {'Authorization': f'JWT token="{data["token"]}"'}
        r2 = self.client.post(self._prefix + '/logout', json={}, headers=headers)
        assert r2.status_code == 200

    def test_login_discourse_success(self):
        """Login with discourse=True + valid sso/sig returns a redirect URL."""
        self.set_discourse_not_mocked()
        sso = 'bm9uY2U9Y2I2ODI1MWVlZmI1MjExZTU4YzAwZmYxMzk1ZjBjMGI%3D%0A'
        sig = '2828aa29899722b35a2f191d34ef9b3ce695e0e6eeec47deb46d588d70c7cb56'

        from c2corg_api.models.user import User as _User

        moderator = (
            self.session.query(_User).filter(_User.username == 'moderator').one()
        )
        # Get the expected redirect from the real (un-mocked) discourse client
        from c2corg_api.security.discourse_client import get_discourse_client

        real_client = get_discourse_client(settings)
        expected_redirect = real_client.redirect(moderator, sso, sig)

        r = self._login('moderator', discourse=True, sso=sso, sig=sig)
        assert r.status_code == 200
        data = r.json()
        assert 'token' in data
        assert data.get('redirect') == expected_redirect

    def test_renew_token_different_success(self):
        """Two renew calls spaced >1 s apart produce different tokens."""
        import time

        r = self._login('contributor')
        assert r.status_code == 200
        token1 = r.json()['token']

        time.sleep(1.01)

        headers = {'Authorization': f'JWT token="{token1}"'}
        r2 = self.client.post(self._prefix + '/renew', headers=headers)
        assert r2.status_code == 200
        token2 = r2.json()['token']
        assert token1 != token2

        # token2 is still valid
        headers2 = {'Authorization': f'JWT token="{token2}"'}
        r3 = self.client.get(self._prefix + '/account', headers=headers2)
        assert r3.status_code == 200
        assert r3.json()['name'] == 'Contributor'

        # Clean up both tokens
        self.client.post(self._prefix + '/logout', json={}, headers=headers)
        self.client.post(self._prefix + '/logout', json={}, headers=headers2)


class TestUserRouterPasswordChangeExtra(BaseUserTestRouter):
    """forgot-password tests with Discourse down."""

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_forgot_password_discourse_down(self, _send_email):
        """Password reset should succeed even when Discourse is unavailable
        because the password change itself does not require Discourse."""
        self.set_discourse_down()
        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        assert user is not None
        initial_password = user.password

        r = self.client.post(
            self._prefix + '/request_password_change', json={'email': user.email}
        )
        assert r.status_code == 200

        nonce = self.extract_nonce(_send_email, 'change_password')
        r2 = self.client.post(
            self._prefix + '/validate_new_password/' + nonce,
            json={'password': 'new pass'},
        )
        assert r2.status_code == 200

        self.session.expunge(user)
        user = self.session.get(User, user_id)
        assert user is not None
        assert user.validation_nonce is None
        assert user.password != initial_password


class TestUserRouterJobs(BaseUserTestRouter):
    """Tests for background-job helpers (purge_account, purge_token)."""

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_purge_accounts(self, _send_email):
        """Un-confirmed accounts whose nonce has expired are removed by
        the purge_account job; still-valid nonces are kept."""
        from datetime import datetime, timezone

        from c2corg_api.jobs.purge_non_activated_accounts import purge_account

        body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        r = self.client.post(self._prefix + '/register', json=body)
        assert r.status_code == 200

        query = self.session.query(User).filter(User.username == 'test')

        # Nonce not yet expired → user survives the purge
        purge_account(self.session)
        assert query.count() == 1

        # Expire the nonce
        user = query.one()
        user.validation_nonce_expire = datetime.now(timezone.utc)
        self.session.flush()

        # Nonce expired → user is removed
        purge_account(self.session)
        assert query.count() == 0

    def test_purge_tokens(self):
        """Tokens whose expire timestamp is in the past are removed by the
        purge_token job; valid tokens are kept."""
        from datetime import datetime, timezone

        from c2corg_api.jobs.purge_expired_tokens import purge_token
        from c2corg_api.models.token import Token

        r = self.client.post(
            self._prefix + '/login',
            json={'username': 'moderator', 'password': global_passwords['moderator']},
        )
        assert r.status_code == 200
        token_value = r.json()['token']

        query = self.session.query(Token).filter(Token.value == token_value)

        # Token still valid → not removed
        purge_token(self.session)
        assert query.count() == 1

        # Expire the token
        token = query.one()
        token.expire = datetime.now(timezone.utc)
        self.session.flush()

        # Token expired → removed
        purge_token(self.session)
        assert query.count() == 0

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_register_search_index(self, _send_email):
        """Tests that user accounts are only indexed once they are confirmed.

        Before email validation the profile must NOT appear in the ES
        search index.  After validation it must.
        """
        from c2corg_api.models.user_profile import USERPROFILE_TYPE
        from c2corg_api.scripts.es.sync import sync_es
        from c2corg_api.search import elasticsearch_config, search_documents

        request_body = {
            'username': 'test',
            'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org',
        }
        url = self._prefix + '/register'

        r = self.client.post(url, json=request_body)
        assert r.status_code == 200
        body = r.json()
        assert 'id' in body
        user_id = body['id']

        # check that the profile is not inserted in the search index
        sync_es(self.session)
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id, index=elasticsearch_config['index'], ignore=404
        )
        assert search_doc is None

        # Simulate confirmation email validation
        nonce = self.extract_nonce(_send_email, 'validate_register_email')
        url_api_validation = self._prefix + '/validate_register_email/%s' % nonce
        r = self.client.post(url_api_validation, json={})
        assert r.status_code == 200

        # check that the profile is inserted in the index after confirmation
        sync_es(self.session)
        from c2corg_api.tests.search import force_search_index

        force_search_index()
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id, index=elasticsearch_config['index']
        )
        assert search_doc is not None
        assert search_doc['doc_type'] is not None
        assert search_doc['title_fr'] == 'Max Mustermann testf'
