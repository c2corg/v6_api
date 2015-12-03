# -*- coding: utf-8 -*-
from c2corg_api.models.user import User

from c2corg_api.tests.views import BaseTestRest


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

    def login(self, username, password=None, status=200):
        if not password:
            password = self.global_passwords[username]

        request_body = {
            'username': username,
            'password': password
            }

        url = '/users/login'
        response = self.app.post_json(url, request_body, status=status)
        return response

    def test_login_success(self):
        body = self.login('moderator', status=200).json
        self.assertTrue('token' in body)

    def test_login_failure(self):
        body = self.login('moderator', password='invalid', status=403).json
        self.assertEqual(body['status'], 'error')

    def assertExpireAlmostEqual(self, expire, days, seconds_delta):  # noqa
        import time
        now = int(round(time.time()))
        expected = days * 24 * 3600 + now  # 14 days from now
        if (abs(expected - expire) > seconds_delta):
            raise self.failureException, \
                    '%r == %r within %r seconds' % \
                    (expected, expire, seconds_delta)

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
        print 'Waiting for more than 1s to get a different token'
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

    def _add_test_data(self):
        pass
