"""Run the view logic written for Pyramid on a FastAPI request."""
# The validators of views/validation.py and the document view classes read a
# small part of the Pyramid request: GET, matchdict, validated, errors,
# If-None-Match, Authorization, the response headers, the user and its
# permissions. This
# adapter gives them that interface, so the moved routes keep exactly the
# same logic, checks and messages while they move (#2365).

import json
import re

import transaction
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from c2corg_api.httpexceptions import HTTPError, HTTPNotModified, HTTPRedirection
from c2corg_api.models.user import AccountNotValidated
from c2corg_api.views.resource import Errors
from c2corg_api.web.auth import parse_authorization
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response


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
        self.response = _Response()
        # as WebOb's request.if_none_match: weak ETags count
        self.if_none_match = parse_if_none_match(request.headers.get('If-None-Match'))
        self.registry = request.app.state.registry
        self._user = user
        # as WebOb's request.authorization: (type, params), or None
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


def validate_origin(request, **kwargs):
    """Refuse an origin the CORS policy does not allow, as Cornice."""
    # Cornice runs it as the first validator of every view: after the token,
    # the rate limiting, the content type and the permission, and its error
    # comes with those of the other validators.
    from c2corg_api.web.cors import origin_allowed

    origin = request.headers.get('Origin')
    if origin and not origin_allowed(origin):
        request.errors.add('header', 'Origin', f'{origin} not allowed')


def validate_query(request, *validators, user=None):
    """Run the validators; return (adapted request, error answer or None)."""
    adapted = ValidatedRequest(request, user)
    try:
        for validator in (validate_origin, *validators):
            validator(adapted)
    except HTTPError as e:
        # a validator may raise, as the views do (e.g. an invalid waypoint id)
        return adapted, _http_error(e)
    if adapted.errors:
        return adapted, error_response(adapted.errors, adapted.errors.status)
    return adapted, None


def run_view(adapted, view):
    """Call a view, and turn the HTTP exceptions it raises into answers."""
    try:
        result = _call_view(adapted, view)
    except HTTPNotModified as e:
        # only the cache headers, like the Pyramid answer
        headers = {k: v for k, v in e.headers.items() if k in ('ETag', 'Cache-Control')}
        return Response(status_code=304, headers=headers)
    except HTTPRedirection as e:
        return _redirection(e)
    except HTTPError as e:
        return _http_error(e)
    except AccountNotValidated as e:
        return _account_not_validated(e)
    if adapted.errors:
        # as Cornice: the errors the view itself adds are the answer
        return error_response(adapted.errors, adapted.errors.status)
    return _render(adapted, result)


def _call_view(adapted, view):
    """Call a view, and raise the redirection it may return."""
    result = view()
    if isinstance(result, HTTPRedirection):
        # returned, not raised (the image proxy)
        raise result
    return result


def _render(adapted, result):
    """Answer what a view returned."""
    if isinstance(result, Response):
        # a response of its own: the progress stream of the Navitia jobs
        return result
    headers = adapted.response.headers
    content_type = adapted.response.content_type
    if content_type is not None:
        # a string, with the content type of the Pyramid string renderer
        headers = {**headers, 'Content-Type': f'{content_type}; charset=UTF-8'}
        return Response(result, headers=headers)
    status = adapted.response.status
    if status is not None:
        # an int, or a status line ('404 Not Found') as WebOb accepts
        return JSONResponse(
            result, status_code=int(str(status).split()[0]), headers=headers
        )
    if not headers:
        return result
    return JSONResponse(result, headers=headers)


def _redirection(e):
    """Answer a redirection with its status, headers and text body."""
    # the text body of WebOb, which answered the redirections of Pyramid
    body = (
        f'{e.code} {e.title}\n\nThe resource was found at {e.location}; '
        'you should be redirected automatically.\n\n'
    )
    headers = {**e.headers, 'Content-Type': 'text/plain; charset=UTF-8'}
    return Response(body, status_code=e.code, headers=headers)


def _account_not_validated(e):
    """Answer like the exception view of Pyramid for AccountNotValidated."""
    # e.g. the password change of an account whose email is not validated
    return error_response(
        [{'location': 'body', 'name': 'Error', 'description': list(e.args)}]
    )


def _http_error(e):
    """Answer an HTTP error as Pyramid did: its title and detail."""
    return error_response([('body', e.title, e.detail)], e.code)


def serve_view(
    request,
    user,
    validators,
    view_class,
    method='get',
    permission=None,
    content_types=None,
):
    """Answer a request with a method of a Pyramid view class."""
    refused = _refused(request, user, view_class, method, permission, content_types)
    if refused is not None:
        return refused
    adapted, error = validate_query(request, *validators, user=user)
    if error is not None:
        return error
    with request_session():
        return run_view(adapted, getattr(view_class(adapted), method))


def _refused(request, user, view_class, method, permission, content_types):
    """Answer the 415 or the 403 of Pyramid, or None."""
    # as Cornice: a request with another Content-Type than those of the view
    # (json_view) is refused, before the permission check; none is accepted
    if content_types is not None:
        media_type = request.headers.get('Content-Type', '').split(';')[0].strip()
        if media_type and media_type not in content_types:
            description = f'Content-Type header should be one of {content_types}'
            return error_response([('header', 'Content-Type', description)], 415)
    # the permission is checked before the validators, as Pyramid does
    if permission and not ValidatedRequest(request, user).has_permission(permission):
        # the message of Pyramid without debug_authorization (production)
        view_name = f'{view_class.__name__}.{method}__{request.method}'
        description = f'Unauthorized: {view_name} failed permission check'
        return error_response([('body', 'Forbidden', description)], 403)
    return None


async def serve_write(
    request,
    user,
    validators,
    view_class,
    method,
    permission=None,
    content_types=None,
):
    """Answer a write request with a method of a Pyramid view class."""
    # The body is read here, then the view runs in a worker thread, as the
    # sync views do.
    body = await request.body()
    return await run_in_threadpool(
        _serve_write,
        request,
        user,
        body,
        validators,
        view_class,
        method,
        permission,
        content_types,
    )


def _serve_write(
    request, user, body, validators, view_class, method, permission, content_types
):
    # As Pyramid with pyramid_tm, one transaction for the request: what the
    # request raises is rolled back (the 415 and the 403, an HTTP error of a
    # validator or of the view, a bug), what it returns is committed (the
    # validation errors, the answer of the view, and the 429 of the rate
    # limiting with its counters).
    from c2corg_api.tweens.rate_limiting import rate_limit_error
    from c2corg_api.views import invalid_json_body

    adapted = ValidatedRequest(request, user, body=body)
    with request_session():
        # the rate limiting runs first, as its tween did: before the content
        # type, the permission and the validators
        error = rate_limit_error(adapted, adapted.registry.settings)
        if error is not None:
            transaction.commit()
            return _http_error(error)
        refused = _refused(request, user, view_class, method, permission, content_types)
        if refused is not None:
            return refused
        try:
            for validator in (validate_origin, *validators):
                validator(adapted)
            if adapted.errors:
                transaction.commit()
                return error_response(adapted.errors, adapted.errors.status)
            result = _call_view(adapted, getattr(view_class(adapted), method))
        except HTTPRedirection as e:
            return _redirection(e)
        except HTTPError as e:
            return _http_error(e)
        except AccountNotValidated as e:
            return _account_not_validated(e)
        except Exception:
            # a view reading an invalid JSON body fails on it: an error of the
            # client, answered as the catch-all error view of Pyramid does
            reason = invalid_json_body(adapted)
            if reason is None:
                raise
            return error_response([('body', '', f'Invalid JSON: {reason}')])
        if adapted.errors:
            # as Cornice: the errors the view itself adds are the answer
            # (e.g. a failed login, 401), returned and so committed
            transaction.commit()
            return error_response(adapted.errors, adapted.errors.status)
        response = _render(adapted, result)
        transaction.commit()
        return response
