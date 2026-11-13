"""The request as the validators and the views read it."""
# The validators of views/validation.py and the views read a small part of
# the Pyramid request they were written for: GET, matchdict, validated,
# errors, If-None-Match, Authorization, the response headers, the user and
# its permissions. ValidatedRequest gives them that interface over the
# FastAPI request.

import json
import re

from c2corg_api.views.resource import Errors
from c2corg_api.web.auth import parse_authorization


class _Response:
    """What the views set on request.response: headers and content type."""

    def __init__(self):
        self.headers = {}
        # set by the views answering something else than JSON (the XML sitemaps)
        self.content_type = None
        # set by the views answering another status (the stop areas: 404)
        self.status = None


# an ETag of If-None-Match, weak (W/"...") or strong ("..."), as WebOb read them
_ETAG = re.compile(r'(?:^|\s)(W/)?"((?:\\"|.)*?)"')


class _AnyETag:
    """If-None-Match: *, which matches any ETag."""

    def __contains__(self, etag):
        return True


def parse_if_none_match(value):
    """Return the ETags of If-None-Match, weak ones included, as WebOb did."""
    if value == '*':
        return _AnyETag()
    if not value:
        return ()
    matches = _ETAG.findall(value)
    if not matches:
        return (value,)
    return tuple(etag for _, etag in matches)


class ValidatedRequest:
    """The part of a Pyramid request the view logic uses."""

    def __init__(self, request, user=None, path_params=None, body=b''):
        self.method = request.method
        self.url = str(request.url)
        self.path = request.url.path
        self.remote_addr = request.client.host if request.client else None
        self.cookies = request.cookies
        self.GET = request.query_params
        self.params = request.query_params
        self.headers = request.headers
        self.matchdict = dict(path_params or request.path_params)
        self.validated = {}
        self.errors = Errors()
        # the validation errors of the body, answered as FastAPI does (422)
        self.invalid = []
        self.response = _Response()
        # as WebOb's request.if_none_match: weak ETags count
        self.if_none_match = parse_if_none_match(request.headers.get('If-None-Match'))
        self.registry = request.app.state.registry
        self._user = user
        # the scheme and token of the Authorization header, or None
        self.authorization = parse_authorization(request.headers.get('Authorization'))
        # the body of a write, read by the validators (extract_body) and the views
        # as WebOb gives it: the media type without its parameters, and the
        # JSON body raising a ValueError when it is not JSON
        self.body = body
        content_type, _, parameters = request.headers.get('Content-Type', '').partition(
            ';'
        )
        self.content_type = content_type.strip()
        charset = parameters.strip().partition('charset=')[2]
        self.charset = charset.strip().strip('"') or 'UTF-8'
        # the form fields: the JSON views have none
        self.POST = {}

    @property
    def client_addr(self):
        # as WebOb: the first address of X-Forwarded-For, else the peer
        forwarded_for = self.headers.get('X-Forwarded-For')
        if forwarded_for is not None:
            return forwarded_for.split(',')[0].strip()
        return self.remote_addr

    @property
    def json_body(self):
        return json.loads(self.body.decode(self.charset))

    @property
    def json(self):
        return self.json_body

    @property
    def authenticated_userid(self):
        return None if self._user is None else self._user.id

    def has_permission(self, permission):
        """Answer like the ACLs of the Pyramid application."""
        if self._user is None:
            return False
        if permission == 'moderator':
            return self._user.is_moderator
        return permission == 'authenticated'
