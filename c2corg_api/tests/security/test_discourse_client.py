"""Tests for the Discourse API client wrapper."""

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

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


def _signed(params):
    """Return a payload of the params and its signature with SETTINGS' key."""
    payload = base64.b64encode(urlencode(params).encode('utf-8')).decode('ascii')
    key = SETTINGS['discourse.sso_secret'].encode('utf-8')
    sig = hmac.new(key, payload.encode('utf-8'), digestmod=hashlib.sha256)
    return payload, sig.hexdigest()


class TestSsoProvider:
    """Check the SSO payloads of the forum, under `python -O` too."""

    client = APIDiscourseClient(SETTINGS)

    def test_decode_payload(self):
        """Return the parameters of a payload."""
        payload, _ = _signed({'nonce': 'n', 'return_sso_url': 'https://x'})
        params = self.client.decode_payload(payload)
        assert params == {'nonce': ['n'], 'return_sso_url': ['https://x']}

    @pytest.mark.parametrize(
        'payload',
        [
            '',
            'not base64!',
            base64.b64encode(b'\xff\xfe').decode('ascii'),
            base64.b64encode(b'return_sso_url=https://x').decode('ascii'),
            base64.b64encode(b'nonce=').decode('ascii'),
        ],
    )
    def test_decode_payload_refuses(self, payload):
        """Raise a ValueError for a payload without a nonce or not decodable."""
        with pytest.raises(ValueError):
            self.client.decode_payload(payload)

    @pytest.mark.parametrize(
        'params',
        [
            {'return_sso_url': 'https://forum.test/session/sso_login'},
            {'nonce': 'n'},
        ],
    )
    def test_redirect_refuses_a_signed_payload_missing_a_value(self, params):
        """Answer a 400, not a 500, for a signed payload missing a value."""
        payload, sig = _signed(params)
        with pytest.raises(HTTPBadRequest):
            self.client.redirect(MagicMock(), payload, sig)

    @patch('c2corg_api.security.discourse_client.requests.get')
    def test_request_nonce_refuses_another_status(self, get):
        """Raise when the forum does not answer with a redirect."""
        get.return_value = MagicMock(status_code=200)
        with pytest.raises(Exception, match='Could not request nonce'):
            self.client.request_nonce()

    @patch('c2corg_api.security.discourse_client.requests.get')
    def test_request_nonce(self, get):
        """Return the nonce of the signed redirect of the forum."""
        payload, sig = _signed({'nonce': 'the-nonce'})
        location = (
            f'https://forum.test/session/sso?{urlencode({"sso": payload, "sig": sig})}'
        )
        get.return_value = MagicMock(status_code=302, headers={'Location': location})
        assert self.client.request_nonce() == 'the-nonce'
