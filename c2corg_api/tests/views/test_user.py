# -*- coding: utf-8 -*-
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile

from c2corg_api.tests.views import BaseTestRest
from c2corg_api.security.discourse_sso_provider import discourse_redirect


class TestUserRest(BaseTestRest):

    def setUp(self):  # noqa
        self._prefix = "/users"
        self._model = User
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_register(self):
        request_body = {
            'username': 'test',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        # First succeed in creating a new user
        body = self.app.post_json(url, request_body, status=200).json
        self.assertBodyEqual(body, 'username', 'test')
        self.assertBodyEqual(body, 'email', 'some_user@camptocamp.org')
        self.assertNotIn('password', body)
        self.assertIn('id', body)
        user_id = body.get('id')
        self.assertIsNotNone(self.session.query(User).get(user_id))
        profile = self.session.query(UserProfile).get(user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(len(profile.versions), 1)

        # Now reject non unique attributes
        body = self.app.post_json(url, request_body, status=400).json
        self.assertErrorsContain(body, 'email')
        self.assertErrorsContain(body, 'username')

        # Require username, password and email attributes
        body = self.app.post_json(url, {}, status=400).json
        self.assertErrorsContain(body, 'email')
        self.assertErrorsContain(body, 'username')
        self.assertErrorsContain(body, 'password')

        # Usage of utf8 password
        request_utf8 = {
            'username': 'utf8',
            'password': 'élève 日本',
            'email': 'utf8@camptocamp.org'
        }
        body = self.app.post_json(url, request_utf8, status=200).json

    def login(self, username, password=None, status=200, sso=None, sig=None,
              discourse=None):
        if not password:
            password = self.global_passwords[username]

        request_body = {
            'username': username,
            'password': password
            }

        if sso:
            request_body['sso'] = sso
        if sig:
            request_body['sig'] = sig
        if discourse:
            request_body['discourse'] = discourse

        url = '/users/login'
        response = self.app.post_json(url, request_body, status=status)
        return response

    def test_login_success(self):
        body = self.login('moderator', status=200).json
        self.assertTrue('token' in body)

    def test_login_discourse_success(self):
        # noqa See https://meta.discourse.org/t/official-single-sign-on-for-discourse/13045
        sso = "bm9uY2U9Y2I2ODI1MWVlZmI1MjExZTU4YzAwZmYxMzk1ZjBjMGI%3D%0A"
        sig = "2828aa29899722b35a2f191d34ef9b3ce695e0e6eeec47deb46d588d70c7cb56"  # noqa

        moderator = self.session.query(User).filter(
                User.username == 'moderator').one()
        redirect1 = discourse_redirect(moderator, sso, sig, self.settings)

        body = self.login('moderator', sso=sso, sig=sig, discourse=True).json
        self.assertTrue('token' in body)
        redirect2 = body['redirect']

        self.assertEqual(redirect1, redirect2)

    def test_login_failure(self):
        body = self.login('moderator', password='invalid', status=403).json
        self.assertEqual(body['status'], 'error')

    def assertExpireAlmostEqual(self, expire, days, seconds_delta):  # noqa
        import time
        now = int(round(time.time()))
        expected = days * 24 * 3600 + now  # 14 days from now
        if (abs(expected - expire) > seconds_delta):
            raise self.failureException(
                '%r == %r within %r seconds' %
                (expected, expire, seconds_delta))

    def test_login_logout_success(self):
        body = self.login('moderator').json
        token = body['token']
        expire = body['expire']
        self.assertExpireAlmostEqual(expire, 14, 5)

        body = self.post_json_with_token('/users/logout', token)

    def test_renew_success(self):
        restricted_url = '/users/' + str(self.global_userids['contributor'])
        token = self.global_tokens['contributor']

        body = self.post_json_with_token('/users/renew', token)
        expire = body['expire']
        self.assertExpireAlmostEqual(expire, 14, 5)

        token2 = body['token']
        body = self.get_json_with_token(restricted_url, token2, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def test_renew_token_different_success(self):
        # Tokens created in the same second are identical
        restricted_url = '/users/' + str(self.global_userids['contributor'])

        token1 = self.login('contributor').json['token']

        import time
        print('Waiting for more than 1s to get a different token')
        time.sleep(1.01)

        token2 = self.post_json_with_token('/users/renew', token1)['token']
        self.assertNotEquals(token1, token2)

        body = self.get_json_with_token(restricted_url, token2, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

        self.post_json_with_token('/users/logout', token1)
        self.post_json_with_token('/users/logout', token2)

    def test_restricted_request(self):
        url = '/users/' + str(self.global_userids['contributor'])
        body = self.get_json_with_contributor(url, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def test_restricted_request_unauthenticated(self):
        url = '/users/' + str(self.global_userids['contributor'])
        self.app.get(url, status=403)

    def _add_test_data(self):
        pass
