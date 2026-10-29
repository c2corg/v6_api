from types import SimpleNamespace

from c2corg_api.security.roles import extract_token
from c2corg_api.web.auth import parse_authorization


def _request(authorization_header):
    # what roles.extract_token reads: request.authorization (type, params)
    return SimpleNamespace(authorization=parse_authorization(authorization_header))


class TestExtractToken:
    def test_extract_token_legacy_format(self):
        assert extract_token(_request('JWT token="my.jwt.token"')) == 'my.jwt.token'

    def test_extract_token_standard_format(self):
        assert extract_token(_request('JWT my.jwt.token')) == 'my.jwt.token'
