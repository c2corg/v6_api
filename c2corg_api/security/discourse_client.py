import hashlib
import hmac
import logging
import urllib.error
from base64 import b64decode, b64encode
from urllib.parse import parse_qs, urlparse

import requests
from pydiscourse.client import DiscourseClient

from c2corg_api.httpexceptions import HTTPBadRequest

log = logging.getLogger(__name__)


class APIDiscourseClient:
    def __init__(self, settings):
        self.settings = settings
        self.timeout = int(settings['url.timeout'])
        self.discourse_base_url = settings['discourse.url']
        self.discourse_public_url = settings['discourse.public_url']
        self.api_key = settings['discourse.api_key']
        self.sso_key = str(settings.get('discourse.sso_secret'))  # no unicode

        # Hosts a signed SSO payload's return_sso_url is allowed to point
        # to. Our own discourse.public_url is always allowed (that's the
        # only thing this ever pointed to before multi-instance support
        # was added); extra hosts (e.g. a beta instance sharing the same
        # sso_secret during a migration) are opt-in via settings, comma
        # separated.
        extra_hosts = settings.get('discourse.allowed_sso_hosts', '')
        self.allowed_sso_hosts = {
            urlparse(self.discourse_public_url).hostname,
        } | {host.strip() for host in extra_hosts.split(',') if host.strip()}

        self.discourse_userid_cache = {}

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
        return discourse_userid

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

    def invite_user_to_topic(self, username, topic_id):
        """Invite a forum user, by username, to a topic."""
        # pydiscourse only invites by e-mail (invite_user_to_topic); the
        # c2corg fork used to add this call by username.
        return self.client._post(f'/t/{topic_id}/invite.json', user=username)

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
            raise HTTPBadRequest('discourse login failed')

    def request_nonce(self):
        url = f'{self.discourse_base_url}/session/sso'
        try:
            r = requests.get(url, allow_redirects=False, timeout=self.timeout)
            assert r.status_code == 302
        except Exception as e:
            log.error('Could not request nonce', exc_info=True)
            raise Exception('Could not request nonce') from e

        location = r.headers['Location']
        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)
        sso = params['sso'][0]
        sig = params['sig'][0]

        self.check_signature(sso, sig)
        payload = self.decode_payload(sso)
        return parse_qs(payload)['nonce'][0]

    def create_response_payload(self, user, nonce, return_sso_url):
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
        r_payload = b64encode(urllib.parse.urlencode(params).encode('utf-8'))
        h = hmac.new(key, r_payload, digestmod=hashlib.sha256)
        qs = urllib.parse.urlencode({'sso': r_payload, 'sig': h.hexdigest()})
        return f'{return_sso_url}?{qs}'

    def get_nonce_from_sso(self, sso, sig):
        payload = urllib.parse.unquote(sso)
        try:
            decoded = self.decode_payload(payload)
        except Exception as e:
            log.error('Failed to decode payload', e)
            raise HTTPBadRequest('discourse login failed') from e

        self.check_signature(payload, sig)

        # return_sso_url tells us which Discourse instance to send the
        # signed response back to, so a single SSO provider can serve
        # several Discourse instances (e.g. prod and a beta instance)
        # sharing the same sso_secret. It's inside the signed payload, so
        # it can't be tampered with in transit - but if the shared secret
        # itself were ever compromised, an attacker could otherwise sign a
        # payload pointing anywhere; only forward users to hosts we
        # explicitly expect, over https.
        qs = parse_qs(decoded)
        return_sso_url = qs['return_sso_url'][0]
        parsed_return_url = urlparse(return_sso_url)
        if (
            parsed_return_url.scheme != 'https'
            or parsed_return_url.hostname not in self.allowed_sso_hosts
        ):
            log.error('return_sso_url not allowed: %s', return_sso_url)
            raise HTTPBadRequest('discourse login failed')

        return qs['nonce'][0], return_sso_url

    def redirect(self, user, sso, signature):
        nonce, return_sso_url = self.get_nonce_from_sso(sso, signature)
        return self.create_response_payload(user, nonce, return_sso_url)

    def redirect_without_nonce(self, user):
        nonce = self.request_nonce()
        return self.create_response_payload(
            user, nonce, f'{self.discourse_public_url}/session/sso_login'
        )


c = None


def get_discourse_client(settings):
    global c
    if c is None:
        c = APIDiscourseClient(settings)
    return c


def set_discourse_client(client):
    global c
    c = client
