from pyramid.httpexceptions import HTTPBadRequest

import base64
import hmac
import hashlib
import urllib

from urlparse import parse_qs

import logging
log = logging.getLogger(__name__)


def decode_payload(payload, key):
    decoded = base64.decodestring(payload)
    assert 'nonce' in decoded
    assert len(payload) > 0
    return decoded


def discourse_redirect(user, sso, signature, settings):
    base_url = '%s/session/sso_login' % settings.get('discourse.url')
    key = str(settings.get('discourse.sso_secret'))  # must not be unicode

    payload = urllib.unquote(sso)
    try:
        decoded = decode_payload(payload, key)
    except Exception as e:
        log.error('Failed to decode payload', e)
        raise HTTPBadRequest('discourse login failed')

    h = hmac.new(key, payload, digestmod=hashlib.sha256)
    this_signature = h.hexdigest()

    if this_signature != signature:
        log.error('Signature mismatch')
        raise HTTPBadRequest('discourse login failed')

    # Build the return payload

    qs = parse_qs(decoded)
    params = {
        'nonce': qs['nonce'][0],
        'email': user.email,
        'external_id': user.id,
        'username': user.username,
        'name': user.username,
    }

    return_payload = base64.encodestring(urllib.urlencode(params))
    h = hmac.new(key, return_payload, digestmod=hashlib.sha256)
    qs = urllib.urlencode({'sso': return_payload, 'sig': h.hexdigest()})
    return '%s?%s' % (base_url, qs)
