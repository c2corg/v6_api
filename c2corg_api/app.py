"""The FastAPI application of the API."""
# Served by uvicorn (c2corg_api.asgi); the tests drive it through FastAPI's
# TestClient (c2corg_api.tests.client).

from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from c2corg_api.web import (
    document_actions,
    documents,
    feeds,
    health,
    history,
    misc,
    navitia,
    openapi,
    params,
    route_suggestions,
    search,
    sitemaps,
    stopareas,
    user_actions,
    users,
)
from c2corg_api.web.auth import TokenValidationMiddleware
from c2corg_api.web.checks import Refused, refused_response
from c2corg_api.web.cors import CorsMiddleware
from c2corg_api.web.errors import UnexpectedErrorMiddleware, error_response


class Registry:
    """The settings and the configuration the views read (request.registry)."""

    def __init__(self, settings, **attributes):
        self.settings = settings
        # queue_config, feed_admin_user_account_id, anonymous_user_id
        for name, value in attributes.items():
            setattr(self, name, value)


def threads(settings):
    """Return how many requests a uvicorn worker serves at once."""
    # `server.threads`, else the size of the database pool of the worker
    return int(
        settings.get('server.threads') or settings.get('sqlalchemy.pool_size') or 5
    )


def _lifespan(threads):
    @asynccontextmanager
    async def lifespan(app):
        # The routes are plain functions: on uvicorn workers, each request
        # runs in a thread, 40 at once by default. That many requests at once
        # overload the database and Elasticsearch (see #2448): the others
        # wait here for a thread instead. Gunicorn's sync workers serve one
        # request at a time, and do not run this.
        to_thread.current_default_thread_limiter().total_tokens = threads
        yield

    return lifespan


def create_fastapi_app(settings, registry=None):
    """Return the FastAPI application of the API."""
    # no generated docs: the API documentation is not served (yet); no
    # redirection of a path with a trailing slash: it is not found, as on
    # Pyramid
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=_lifespan(threads(settings)),
    )
    app.state.settings = settings
    app.state.registry = registry or Registry(settings)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, params.validation_error)
    app.add_exception_handler(Refused, refused_response)
    # the last middleware added runs first: CORS wraps the token errors and
    # the unexpected errors
    app.add_middleware(UnexpectedErrorMiddleware)
    app.add_middleware(TokenValidationMiddleware)
    app.add_middleware(CorsMiddleware)
    health.include(app)
    search.include(app)
    documents.include(app)
    history.include(app)
    feeds.include(app)
    sitemaps.include(app)
    stopareas.include(app)
    route_suggestions.include(app)
    misc.include(app)
    users.include(app)
    navitia.include(app)
    user_actions.include(app)
    document_actions.include(app)
    if openapi.enabled(settings):
        openapi.include(app)
    return app


async def _http_exception(request, exc):
    """Answer an unknown route (404) or method (405)."""
    # a 404 gives the path, as Pyramid did; a 405 the methods to use, also
    # in its Allow header
    headers = None
    if exc.status_code == 404:
        description = request.url.path
    elif exc.status_code == 405:
        allowed = _allowed_methods(request)
        description = f'{request.method} is not allowed here: use {", ".join(allowed)}'
        headers = {'Allow': ', '.join(allowed)}
    else:
        description = None
    return error_response(
        [('body', _REASONS.get(exc.status_code, exc.detail), description)],
        exc.status_code,
        headers,
    )


def _allowed_methods(request):
    """Return the methods of all the routes of the path of a request."""
    # Starlette's Allow header names the methods of the first route of the
    # path only, while a path may have several (GET and POST /waypoints)
    methods = set()
    for route in request.app.router.routes:
        if (
            isinstance(route, APIRoute)
            and route.matches(request.scope)[0] != Match.NONE
        ):
            methods |= route.methods
    return sorted(methods - {'HEAD'})


_REASONS = {404: 'Not Found', 405: 'Method Not Allowed'}
