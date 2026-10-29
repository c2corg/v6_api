from unittest.mock import patch

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_users import UserContractTest

ANONYMOUS_LIMIT = 'c2corg_api.tweens.rate_limiting._is_anonymous_request_rate_limited'

# dummy credentials of the tests, refused or never checked
WRONG_PASSWORD = 'wrong'  # nosec B105
NEW_PASSWORD = 'a new password'  # nosec B105
WRONG_SSO_SECRET = 'wrong'  # nosec B105


class TestLoginWrites(UserContractTest):
    @contract(('POST', '/users/login'))
    def test_anonymous_rate_limit(self):
        # the login is rate limited by client IP, read from X-Forwarded-For
        with patch(ANONYMOUS_LIMIT, return_value=True) as limited:
            response = self.post(
                '/users/login',
                {'username': 'contributor', 'password': WRONG_PASSWORD},
                headers={'X-Forwarded-For': '203.0.113.7, 10.0.0.1'},
                status=429,
            )
        check_snapshot('users_login_rate_limited', response)
        key = limited.call_args.args[1]
        assert key.endswith(':ratelimit:anon:login:203.0.113.7')

    @contract(
        ('POST', '/users/renew'),
        ('POST', '/users/logout'),
        ('POST', '/users/discourse-redirect'),
        ('POST', '/users/update_preferred_language'),
        ('POST', '/users/account'),
    )
    def test_reserved_to_the_users(self):
        for path in (
            '/users/renew',
            '/users/logout',
            '/users/discourse-redirect',
            '/users/update_preferred_language',
            '/users/account',
        ):
            response = self.post(path, {}, status=403)
            check_snapshot('users_write_anonymous', response)


class TestAccountWrites(UserContractTest):
    @contract(('POST', '/users/account'))
    def test_wrong_current_password(self):
        body = {'currentpassword': WRONG_PASSWORD, 'name': 'Other name'}
        response = self.post('/users/account', body, user='contributor', status=400)
        check_snapshot('users_account_wrong_password', response)

    @contract(('POST', '/users/update_preferred_language'))
    def test_invalid_language(self):
        response = self.post(
            '/users/update_preferred_language',
            {'lang': 'xx'},
            user='contributor',
            status=400,
        )
        check_snapshot('users_update_preferred_language_invalid', response)


class TestRegistrationWrites(UserContractTest):
    @contract(('POST', '/users/register'))
    def test_invalid_registration(self):
        response = self.post('/users/register', {'username': 'x'}, status=400)
        check_snapshot('users_register_invalid', response)

    @contract(('POST', '/users/request_password_change'))
    def test_password_change_of_an_unknown_email(self):
        response = self.post(
            '/users/request_password_change',
            {'email': 'nobody@example.org'},
            status=400,
        )
        check_snapshot('users_request_password_change_unknown', response)

    @contract(
        ('POST', '/users/validate_register_email/{nonce}'),
        ('POST', '/users/validate_new_password/{nonce}'),
        ('POST', '/users/validate_change_email/{nonce}'),
    )
    def test_invalid_nonce(self):
        for path in (
            '/users/validate_register_email/not-a-nonce',
            '/users/validate_new_password/not-a-nonce',
            '/users/validate_change_email/not-a-nonce',
        ):
            body = {'password': NEW_PASSWORD} if 'password' in path else {}
            response = self.post(path, body, status=400)
            check_snapshot('users_invalid_nonce', response)


class TestSsoWrites(UserContractTest):
    @contract(('POST', '/sso_sync'), ('POST', '/sso_login'))
    def test_refused(self):
        response = self.post(
            '/sso_sync', {'sso_key': WRONG_SSO_SECRET, 'external_id': '1'}, status=403
        )
        check_snapshot('sso_sync_wrong_key', response)
        response = self.post('/sso_login', {'token': WRONG_SSO_SECRET}, status=403)
        check_snapshot('sso_login_wrong_token', response)
