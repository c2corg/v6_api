import jwt
import unittest

from webob import Request

from c2corg_api.security.jwt_policy import IntegerSubJWTAuthenticationPolicy
from c2corg_api.security.roles import extract_token


class TestIntegerSubJWTAuthenticationPolicy(unittest.TestCase):

    def setUp(self):
        self.secret = 'a_long_enough_secret_key_for_hs256_testing'
        self.policy = IntegerSubJWTAuthenticationPolicy(
            private_key=self.secret,
            algorithm='HS256',
            auth_type='JWT',
        )
        self.claims = {
            'sub': '12345',
            'username': 'testuser',
        }
        self.token = jwt.encode(
            self.claims, self.secret, algorithm='HS256')

    def _make_request(self, authorization_header=None):
        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/'}
        if authorization_header:
            environ['HTTP_AUTHORIZATION'] = authorization_header
        request = Request(environ)
        # Attach jwt_claims for unauthenticated_userid
        request.jwt_claims = self.policy.get_claims(request)
        return request

    def test_get_claims_legacy_format(self):
        """JWT token="<token>" format used by the frontend."""
        request = self._make_request(
            'JWT token="' + self.token + '"')
        claims = self.policy.get_claims(request)
        self.assertEqual(claims['sub'], '12345')
        self.assertEqual(claims['username'], 'testuser')

    def test_get_claims_standard_format(self):
        """JWT <token> format (standard Bearer-style)."""
        request = self._make_request('JWT ' + self.token)
        claims = self.policy.get_claims(request)
        self.assertEqual(claims['sub'], '12345')
        self.assertEqual(claims['username'], 'testuser')

    def test_get_claims_no_authorization(self):
        request = self._make_request()
        claims = self.policy.get_claims(request)
        self.assertEqual(claims, {})

    def test_get_claims_wrong_auth_type(self):
        request = self._make_request('Bearer ' + self.token)
        claims = self.policy.get_claims(request)
        self.assertEqual(claims, {})

    def test_get_claims_invalid_token(self):
        request = self._make_request('JWT not-a-valid-token')
        claims = self.policy.get_claims(request)
        self.assertEqual(claims, {})

    def test_unauthenticated_userid_returns_int(self):
        """sub claim is a string but unauthenticated_userid returns int."""
        request = self._make_request(
            'JWT token="' + self.token + '"')
        userid = self.policy.unauthenticated_userid(request)
        self.assertIsInstance(userid, int)
        self.assertEqual(userid, 12345)

    def test_unauthenticated_userid_standard_format(self):
        request = self._make_request('JWT ' + self.token)
        userid = self.policy.unauthenticated_userid(request)
        self.assertIsInstance(userid, int)
        self.assertEqual(userid, 12345)

    def test_unauthenticated_userid_no_auth(self):
        request = self._make_request()
        request.jwt_claims = {}
        userid = self.policy.unauthenticated_userid(request)
        self.assertIsNone(userid)


class TestExtractToken(unittest.TestCase):

    def _make_request(self, authorization_header):
        environ = {
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/',
            'HTTP_AUTHORIZATION': authorization_header,
        }
        return Request(environ)

    def test_extract_token_legacy_format(self):
        request = self._make_request('JWT token="my.jwt.token"')
        self.assertEqual(extract_token(request), 'my.jwt.token')

    def test_extract_token_standard_format(self):
        request = self._make_request('JWT my.jwt.token')
        self.assertEqual(extract_token(request), 'my.jwt.token')
