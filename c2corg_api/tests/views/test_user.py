# -*- coding: utf-8 -*-
from c2corg_api.models.user import User

from c2corg_api.tests import BaseTestCase

from nose.plugins.attrib import attr


class TestUserRest(BaseTestCase):

    def setUp(self):  # noqa
        self._prefix = "/users"
        self._model = User
        BaseTestCase.setUp(self)
        self._add_test_data()

    def assertErrorsContain(self, body, key):  # noqa
        for error in body['errors']:
            if error.get('name') == key:
                return
        self.fail(str(body) + " does not contain " + key)

    def assertBodyEqual(self, body, key, expected):  # noqa
        self.assertEqual(body.get(key), expected)

    def get(self, reference):
        url = self._prefix + '/' + str(reference.id)
        response = self.app.get(url, status=200)
        self.assertEqual(response.content_type, 'application/json')
        body = response.json
        self.assertEqual(body.get('id'), reference.id)
        return body

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

    def get_json_with_token(self, url, user, status):
        token = self.global_tokens[user]
        auth = 'JWT token="' + token.encode('ascii') + '"'
        headers = headers = {'Authorization': auth}
        response = self.app.get(url, headers=headers, status=status)
        return response.json

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

    @attr("security")
    def test_login_success(self):
        body = self.login('admin', status=200).json
        self.assertTrue('token' in body)

    @attr("security")
    def test_login_failure(self):
        body = self.login('admin', password='invalid', status=401).json
        self.assertEqual(body['status'], 'error')

    @attr("security")
    def test_restricted_request(self):
        url = '/users/' + str(self.global_userids['contributor'])
        body = self.get_json_with_token(url, user='contributor', status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def _add_test_data(self):
        pass
