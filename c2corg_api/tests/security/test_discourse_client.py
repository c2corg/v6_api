"""Tests for the Discourse API client wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    DisabledDiscourseClient,
    discourse_enabled,
    get_discourse_client,
)

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


class TestDisabledDiscourseClient:
    """An API run without a forum (`discourse.enabled = false`)."""

    @pytest.mark.parametrize('value', ['false', 'False', '0', 'no', 'off', ' false '])
    def test_disabled_values(self, value):
        """Read the usual spellings of false as disabled."""
        assert not discourse_enabled({'discourse.enabled': value})

    @pytest.mark.parametrize('settings', [{}, {'discourse.enabled': 'true'}])
    def test_enabled_by_default(self, settings):
        """Keep the forum on unless told otherwise."""
        assert discourse_enabled(settings)

    def test_client_follows_the_setting(self):
        """Build the stand-in when disabled, the real client otherwise."""
        disabled = get_discourse_client({**SETTINGS, 'discourse.enabled': 'false'})
        assert isinstance(disabled, DisabledDiscourseClient)
        assert not disabled.enabled

    def test_real_client_is_enabled(self):
        """Mark the real client as enabled."""
        assert APIDiscourseClient(SETTINGS).enabled

    @patch('pydiscourse.client.requests.request')
    @patch('c2corg_api.security.discourse_client.requests.get')
    def test_never_calls_the_forum(self, get, request):
        """Do nothing, and send nothing, for what only keeps the forum in sync."""
        client = DisabledDiscourseClient()
        user = MagicMock()

        assert client.get_userid(5) is None
        assert client.sync_sso(user) is None
        assert client.logout(5) is None
        assert client.suspend(5, 10, 'reason') is None
        assert client.unsuspend(5) is None
        assert client.invite_user_to_topic('contributor', 10) is None
        assert client.redirect_without_nonce(user) is None
        get.assert_not_called()
        request.assert_not_called()

    def test_refuses_a_discourse_handshake(self):
        """There is no forum to answer a Discourse-initiated login."""
        with pytest.raises(HTTPBadRequest):
            DisabledDiscourseClient().redirect(MagicMock(), 'sso', 'sig')
