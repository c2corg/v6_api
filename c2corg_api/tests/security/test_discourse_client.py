"""Tests for the Discourse API client wrapper."""

from unittest.mock import MagicMock, patch

from c2corg_api.security.discourse_client import APIDiscourseClient

SETTINGS = {
    'url.timeout': '10',
    'discourse.url': 'http://discourse.test',
    'discourse.public_url': 'https://forum.test',
    'discourse.api_key': 'the-api-key',
    'discourse.sso_secret': 'the-sso-secret',
}


def _ok_response(body):
    """Build a successful JSON response from the Discourse API."""
    response = MagicMock(ok=True, status_code=200)
    response.headers = {'content-type': 'application/json; charset=utf-8'}
    response.json.return_value = body
    return response


class TestAPIDiscourseClient:
    """Check the requests APIDiscourseClient sends to Discourse."""

    @patch('pydiscourse.client.requests.request')
    def test_api_key_sent_in_headers(self, request):
        """Send the API key as headers, never in the URL."""
        # Discourse no longer accepts api_key/api_username as query
        # parameters (the c2corg pydiscourse fork sent them that way).
        request.return_value = _ok_response(
            {'user': {'id': 42, 'username': 'contributor'}}
        )

        client = APIDiscourseClient(SETTINGS)
        assert client.get_userid(5) == 42

        verb, url = request.call_args.args
        kwargs = request.call_args.kwargs
        assert verb == 'GET'
        assert url == 'http://discourse.test/users/by-external/5'
        assert kwargs['headers']['Api-Key'] == 'the-api-key'
        assert kwargs['headers']['Api-Username'] == 'system'
        params = kwargs.get('params') or {}
        assert 'api_key' not in params
        assert 'api_username' not in params

    @patch('pydiscourse.client.requests.request')
    def test_invite_user_to_topic(self, request):
        """Invite a user to a topic by username."""
        request.return_value = _ok_response({})

        APIDiscourseClient(SETTINGS).invite_user_to_topic('contributor', 10)

        verb, url = request.call_args.args
        assert verb == 'POST'
        assert url == 'http://discourse.test/t/10/invite.json'
        assert request.call_args.kwargs['data'] == {'user': 'contributor'}
