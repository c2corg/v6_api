"""Run the view logic written for Pyramid on a FastAPI request."""
# The validators of views/validation.py and the document view classes read a
# small part of the Pyramid request: GET, matchdict, validated, errors,
# If-None-Match, the response headers, the user and its permissions. This
# adapter gives them that interface, so the moved routes keep exactly the
# same logic, checks and messages while they move (#2365).

from fastapi.responses import JSONResponse, Response
from pyramid.httpexceptions import HTTPError, HTTPNotModified
from pyramid.threadlocal import manager
from webob.etag import ETagMatcher, NoETag

from c2corg_api.web.errors import error_response


class _Errors(list):
    def add(self, location, name, description):
        self.append((location, name, description))


class _Response:
    """What the views set on request.response: headers only."""

    def __init__(self):
        self.headers = {}


class _Registry:
    """The settings, and the attributes of the Pyramid registry."""

    def __init__(self, settings, pyramid_registry=None):
        self.settings = settings
        self._pyramid_registry = pyramid_registry

    def __getattr__(self, name):
        if self._pyramid_registry is None:
            raise AttributeError(name)
        return getattr(self._pyramid_registry, name)


class ValidatedRequest:
    """The part of a Pyramid request the view logic uses."""

    def __init__(self, request, user=None, path_params=None):
        self.GET = request.query_params
        self.params = request.query_params
        self.headers = request.headers
        self.matchdict = dict(path_params or request.path_params)
        self.validated = {}
        self.errors = _Errors()
        self.response = _Response()
        # as WebOb's request.if_none_match: weak ETags count
        if_none_match = request.headers.get('If-None-Match')
        self.if_none_match = (
            ETagMatcher.parse(if_none_match, strong=False) if if_none_match else NoETag
        )
        self.registry = _Registry(
            request.app.state.settings,
            getattr(request.app.state, 'pyramid_registry', None),
        )
        self._user = user

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


def validate_query(request, *validators, user=None):
    """Run the validators; return (adapted request, error answer or None)."""
    adapted = ValidatedRequest(request, user)
    for validator in validators:
        validator(adapted)
    if adapted.errors:
        return adapted, error_response(adapted.errors)
    return adapted, None


def run_view(adapted, view):
    """Call a view, and turn its Pyramid HTTP exceptions into answers."""
    # Some code reads the Pyramid registry from the thread locals
    # (get_current_registry(), e.g. the image URLs of the markdown cooker):
    # set it for the view, as Pyramid does for its own requests.
    registry = adapted.registry._pyramid_registry
    if registry is not None:
        manager.push({'registry': registry, 'request': None})
    try:
        result = view()
    except HTTPNotModified as e:
        # only the cache headers, like the Pyramid answer
        headers = {k: v for k, v in e.headers.items() if k in ('ETag', 'Cache-Control')}
        return Response(status_code=304, headers=headers)
    except HTTPError as e:
        # like views.http_error_handler
        return error_response([('body', e.title, e.detail)], e.code)
    finally:
        if registry is not None:
            manager.pop()
    headers = adapted.response.headers
    if not headers:
        return result
    return JSONResponse(result, headers=headers)
