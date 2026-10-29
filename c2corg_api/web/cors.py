"""CORS, security headers and HEAD answers, as Cornice gave them to Pyramid views."""
# Cornice answers CORS itself rather than with the usual permissive
# middleware, and clients see the differences: a request from an origin that
# is not allowed gets a 400, preflights answer with a JSON `null` body... The
# contract tests (tests/contract/test_cors.py) pin this behaviour. As Cornice,
# the origin of a request is checked by its first validator (validate_origin
# of web.compat), after the token and the rate limiting: here, only the
# preflights.

import fnmatch

from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from c2corg_api.views import cors_policy
from c2corg_api.web.errors import error_response

# the headers a client may send and read (cors_policy['headers'])
SUPPORTED_HEADERS = ['Content-Type']


def origin_allowed(origin):
    return any(fnmatch.fnmatchcase(origin, o) for o in cors_policy['origins'])


def _route_methods(app, path):
    """Return the methods the routes of `path` accept."""
    methods = []
    scope = {'type': 'http', 'path': path, 'root_path': '', 'method': 'GET'}
    for route in app.router.routes:
        if route.matches(scope)[0] != Match.NONE:
            methods.extend(m for m in route.methods if m not in methods)
    return methods


class CorsMiddleware(BaseHTTPMiddleware):
    """Answer preflights and add the CORS headers, like Cornice."""

    async def dispatch(self, request, call_next):
        origin = request.headers.get('Origin')
        preflight = request.method == 'OPTIONS' and _route_methods(
            request.app, request.url.path
        )
        if preflight:
            response = self._preflight(request, origin)
        else:
            response = await call_next(request)
            if origin and origin_allowed(origin):
                response.headers['Access-Control-Allow-Origin'] = origin
        if not preflight:
            # also on the 404 of a preflight to an unknown path
            response.headers['Access-Control-Expose-Headers'] = ', '.join(
                SUPPORTED_HEADERS
            )
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        if request.method == 'HEAD':
            # the headers of the GET answer, without its body
            headers = dict(response.headers)
            headers.pop('content-length', None)
            return Response(status_code=response.status_code, headers=headers)
        return response

    def _preflight(self, request, origin):
        errors = []
        allowed = False
        if not origin:
            errors.append(('header', 'Origin', 'this header is mandatory'))
        elif origin_allowed(origin):
            allowed = True
        else:
            errors.append(('header', 'Origin', f'{origin} not allowed'))
        method = request.headers.get('Access-Control-Request-Method')
        if not method:
            errors.append(
                ('header', 'Access-Control-Request-Method', 'this header is mandatory')
            )
        headers = {}
        if allowed:
            headers['Access-Control-Allow-Origin'] = origin
        methods = [*_route_methods(request.app, request.url.path), 'OPTIONS']
        if method and method not in methods:
            errors.append(
                ('header', 'Access-Control-Request-Method', 'Method not allowed')
            )
        if errors:
            # Cornice built its error answers anew: only the allowed origin
            # is on them
            return error_response(errors, headers=headers)
        requested = request.headers.get('Access-Control-Request-Headers', '')
        allowed_headers = set(SUPPORTED_HEADERS) | {
            h.strip() for h in requested.split(',') if h.strip()
        }
        headers['Access-Control-Allow-Headers'] = ','.join(allowed_headers)
        headers['Access-Control-Allow-Methods'] = ','.join(methods)
        return JSONResponse(None, headers=headers)
