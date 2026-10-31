"""The OpenAPI document of the routes with typed parameters."""
# Off by default (setting `api.openapi`). Only the routes whose endpoint is
# marked `described` are in it: the others still read their parameters in
# the view classes, so FastAPI knows nothing of them (#2512).

import copy

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute


def enabled(settings):
    """Whether the API serves its OpenAPI document."""
    return str(settings.get('api.openapi', '')).lower() in ('true', '1', 'yes', 'on')


def described_routes(app, excluded=()):
    """Return the routes of the OpenAPI document."""
    return [
        _without_head(route)
        for route in app.router.routes
        if isinstance(route, APIRoute)
        and getattr(route.endpoint, 'described', False)
        and not isinstance(route, excluded)
    ]


def _without_head(route):
    # HEAD answers as GET does, as on every HTTP server: described once
    route = copy.copy(route)
    route.methods = route.methods - {'HEAD'}
    return route


def include(app, excluded=()):
    """Serve /openapi.json, with the described routes only."""

    def openapi():
        if app.openapi_schema is None:
            app.openapi_schema = get_openapi(
                title='camptocamp.org API',
                version=str(app.state.settings.get('cache_version') or '0'),
                routes=described_routes(app, excluded),
            )
        return app.openapi_schema

    app.openapi = openapi
    app.openapi_url = '/openapi.json'
    app.setup()
