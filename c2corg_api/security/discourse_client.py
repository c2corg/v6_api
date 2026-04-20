# Discourse API client.
#
# The HTTP transport layer is heavily inspired by pydiscourse
# (https://github.com/bennylope/pydiscourse), which is licensed under the
# MIT License.
#
# Copyright (c) 2014 Marc Sibson and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import hashlib
import hmac
import logging
from base64 import b64decode, b64encode
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

log = logging.getLogger(__name__)


class DiscourseSSOMismatchError(Exception):
    """Raised when the SSO signature does not match."""

    def __init__(self, message='discourse login failed'):
        super().__init__(message)


# --- Discourse API exceptions (inspired by pydiscourse) ---


class DiscourseError(requests.exceptions.HTTPError):
    """A generic error while attempting to communicate with Discourse."""


class DiscourseServerError(DiscourseError):
    """The Discourse server encountered an error while processing the
    request."""


class DiscourseClientError(DiscourseError):
    """An invalid request has been made."""


# --- Lightweight Discourse HTTP client (inspired by pydiscourse) ---


class DiscourseClient:
    """Minimal Discourse API client that covers only the endpoints used by
    this application."""

    def __init__(self, host, api_username, api_key, timeout=None):
        self.host = host
        self.api_username = api_username
        self.api_key = api_key
        self.timeout = timeout

    # -- public helpers mapped to Discourse endpoints --

    def by_external_id(self, external_id):
        return self._get('/users/by-external/{0}'.format(external_id))['user']

    def create_post(self, content, **kwargs):
        return self._post('/posts', raw=content, **kwargs)

    def invite_user_to_topic_by_username(self, username, topic_id, message=None):
        kwargs = {'user': username}
        if message is not None:
            kwargs['custom_message'] = message
        return self._post('/t/{0}/invite.json'.format(topic_id), **kwargs)

    def log_out(self, userid):
        return self._post('/admin/users/{0}/log_out'.format(userid))

    def suspend(self, userid, duration, reason):
        return self._put(
            '/admin/users/{0}/suspend'.format(userid), duration=duration, reason=reason
        )

    def unsuspend(self, userid):
        return self._put('/admin/users/{0}/unsuspend'.format(userid))

    def sync_sso(self, **kwargs):
        sso_secret = kwargs.pop('sso_secret')
        payload = sso_payload(sso_secret, **kwargs)
        return self._post('/admin/users/sync_sso?{0}'.format(payload), **kwargs)

    # -- HTTP verbs --

    def _get(self, path, **kwargs):
        return self._request('GET', path, params=kwargs)

    def _put(self, path, **kwargs):
        return self._request('PUT', path, data=kwargs)

    def _post(self, path, **kwargs):
        return self._request('POST', path, data=kwargs)

    def _request(self, verb, path, params=None, data=None):
        if params is None:
            params = {}
        if data is None:
            data = {}

        params['api_key'] = self.api_key
        if 'api_username' not in params:
            params['api_username'] = self.api_username

        url = self.host + path
        headers = {'Accept': 'application/json; charset=utf-8'}

        response = requests.request(
            verb,
            url,
            allow_redirects=False,
            params=params,
            data=data,
            headers=headers,
            timeout=self.timeout,
        )

        log.debug('response %s: %s', response.status_code, repr(response.text))

        if not response.ok:
            try:
                msg = ','.join(response.json()['errors'])
            except (ValueError, TypeError, KeyError):
                msg = response.reason or '{0}: {1}'.format(
                    response.status_code, response.text
                )

            if 400 <= response.status_code < 500:
                raise DiscourseClientError(msg, response=response)
            raise DiscourseServerError(msg, response=response)

        if response.status_code == 302:
            raise DiscourseError(
                'Unexpected Redirect, invalid api key or host?', response=response
            )

        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            if not response.content.strip():
                return None
            raise DiscourseError(
                'Invalid Response, expecting JSON got "{0}"'.format(content_type),
                response=response,
            )

        try:
            decoded = response.json()
        except ValueError:
            raise DiscourseError('failed to decode response', response=response)

        if 'errors' in decoded:
            message = decoded.get('message') or ','.join(decoded['errors'])
            raise DiscourseError(message, response=response)

        return decoded


# --- SSO payload helper (inspired by pydiscourse) ---


def sso_payload(secret, **kwargs):
    """Build a signed SSO query-string for Discourse."""
    return_payload = b64encode(urlencode(kwargs).encode('utf-8'))
    h = hmac.new(secret.encode('utf-8'), return_payload, digestmod=hashlib.sha256)
    return urlencode({'sso': return_payload, 'sig': h.hexdigest()})


class APIDiscourseClient(object):
    def __init__(self, settings):
        self.settings = settings
        self.timeout = int(settings['url.timeout'])
        self.discourse_base_url = settings['discourse.url']
        self.discourse_public_url = settings['discourse.public_url']
        self.api_key = settings['discourse.api_key']
        self.sso_key = str(settings.get('discourse.sso_secret'))  # no unicode

        self.discourse_userid_cache = {}
        # FIXME: are we guaranteed usernames can never change? -> no!
        self.discourse_username_cache = {}

        self.client = DiscourseClient(
            self.discourse_base_url,
            api_username='system',  # the built-in Discourse user
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def get_userid(self, userid):
        discourse_userid = self.discourse_userid_cache.get(userid)
        if not discourse_userid:
            discourse_user = self.client.by_external_id(userid)
            discourse_userid = discourse_user['id']
            self.discourse_userid_cache[userid] = discourse_userid
            self.discourse_username_cache[userid] = discourse_user['username']
        return discourse_userid

    def get_username(self, userid):
        discourse_username = self.discourse_username_cache.get(userid)
        if not discourse_username:
            discourse_user = self.client.by_external_id(userid)
            self.discourse_userid_cache[userid] = discourse_user['id']
            discourse_username = discourse_user['username']
            self.discourse_username_cache[userid] = discourse_username
        return discourse_username

    def sync_sso(self, user):
        result = self.client.sync_sso(
            sso_secret=self.sso_key,
            name=user.name,
            username=user.forum_username,
            email=user.email,
            external_id=user.id,
            **{'custom.user_field_1': str(user.id)},
        )
        if result:
            self.discourse_userid_cache[user.id] = result['id']
        return result

    def logout(self, userid):
        discourse_userid = self.get_userid(userid)
        self.client.log_out(discourse_userid)
        return discourse_userid

    def suspend(self, userid, duration, reason):
        discourse_userid = self.get_userid(userid)
        return self.client.suspend(discourse_userid, duration, reason)

    def unsuspend(self, userid):
        discourse_userid = self.get_userid(userid)
        return self.client.unsuspend(discourse_userid)

    # Below this: SSO provider
    def decode_payload(self, payload):
        decoded = b64decode(payload.encode('utf-8')).decode('utf-8')
        assert 'nonce' in decoded
        assert len(payload) > 0
        return decoded

    def check_signature(self, payload, signature):
        key = self.sso_key.encode('utf-8')
        h = hmac.new(key, payload.encode('utf-8'), digestmod=hashlib.sha256)
        this_signature = h.hexdigest()

        if this_signature != signature:
            log.error('Signature mismatch')
            raise DiscourseSSOMismatchError('discourse login failed')

    def request_nonce(self):
        url = '%s/session/sso' % self.discourse_base_url
        try:
            r = requests.get(url, allow_redirects=False, timeout=self.timeout)
            assert r.status_code == 302
        except Exception:
            log.error('Could not request nonce', exc_info=True)
            raise Exception('Could not request nonce')

        location = r.headers['Location']
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        sso = params['sso'][0]
        sig = params['sig'][0]

        self.check_signature(sso, sig)
        payload = self.decode_payload(sso)
        return parse_qs(payload)['nonce'][0]

    def create_response_payload(self, user, nonce, url_part):
        assert nonce is not None, 'No nonce passed'

        params = {
            'nonce': nonce,
            'email': user.email,
            'external_id': user.id,
            'username': user.forum_username,
            'name': user.name,
            'custom.user_field_1': user.id,
        }

        key = self.sso_key.encode('utf-8')
        r_payload = b64encode(urlencode(params).encode('utf-8'))
        h = hmac.new(key, r_payload, digestmod=hashlib.sha256)
        qs = urlencode({'sso': r_payload, 'sig': h.hexdigest()})
        return '%s%s?%s' % (self.discourse_public_url, url_part, qs)

    def get_nonce_from_sso(self, sso, sig):
        payload = unquote(sso)
        try:
            decoded = self.decode_payload(payload)
        except Exception as e:
            log.error('Failed to decode payload', e)
            raise DiscourseSSOMismatchError('discourse login failed')

        self.check_signature(payload, sig)

        # Build the return payload
        qs = parse_qs(decoded)
        return qs['nonce'][0]

    def redirect(self, user, sso, signature):
        nonce = self.get_nonce_from_sso(sso, signature)
        return self.create_response_payload(user, nonce, '/session/sso_login')

    def redirect_without_nonce(self, user):
        nonce = self.request_nonce()
        return self.create_response_payload(user, nonce, '/session/sso_login')


c = None


def get_discourse_client(settings):
    global c
    if c is None:
        c = APIDiscourseClient(settings)
    return c


def set_discourse_client(client):
    global c
    c = client
