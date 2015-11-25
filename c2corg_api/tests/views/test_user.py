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
        body = self.login('moderator', password='invalid', status=401).json
        self.assertEqual(body['status'], 'error')

    def test_restricted_request(self):
        url = '/users/' + str(self.global_userids['contributor'])
        body = self.get_json_with_contributor(url, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def _add_test_data(self):
        pass
