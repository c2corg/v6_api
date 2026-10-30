"""The WSGI application of the API: the FastAPI application."""
# The server is unchanged (gunicorn sync workers, PasteDeploy) until #2449:
# the FastAPI application runs behind an ASGI-to-WSGI bridge.

import re
from contextlib import asynccontextmanager

from a2wsgi import ASGIMiddleware
from anyio import to_thread
from fastapi import FastAPI
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
    search,
    sitemaps,
    stopareas,
    user_actions,
    users,
)
from c2corg_api.web.auth import TokenValidationMiddleware
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
    misc.include(app)
    users.include(app)
    navitia.include(app)
    user_actions.include(app)
    document_actions.include(app)
    _include_non_numeric_ids(app)
    return app


async def _http_exception(request, exc):
    """Answer an unknown route (404) or method (405) like Pyramid did."""
    # Pyramid: the path as description of a 404; Cornice: no description
    # for a 405
    description = request.url.path if exc.status_code == 404 else None
    return error_response(
        [('body', _REASONS.get(exc.status_code, exc.detail), description)],
        exc.status_code,
    )


_REASONS = {404: 'Not Found', 405: 'Method Not Allowed'}


class _NonNumericIdRoute(APIRoute):
    """A route with ids that are not numbers: its validators refuse them."""

    # Pyramid matched any id and the validators answered 400 'invalid id'.
    # The routes match numbers only ({id:int}), so that a fixed path such as
    # /routes/update_public_transportation_rating is not taken for an id.
    # This copy, added after every other route, gives the other ids to the
    # same endpoint, unless a fixed path matches (any method: 405 then).

    fixed_routes = ()

    def matches(self, scope):
        match, child_scope = super().matches(scope)
        if match != Match.NONE and any(
            route.matches(scope)[0] != Match.NONE for route in self.fixed_routes
        ):
            return Match.NONE, {}
        return match, child_scope


_INT_PARAM = re.compile(r'{(\w+):int}')


def _include_non_numeric_ids(app):
    numeric = [
        r
        for r in app.router.routes
        if isinstance(r, APIRoute) and _INT_PARAM.search(r.path)
    ]
    fixed = [
        r for r in app.router.routes if isinstance(r, APIRoute) and '{' not in r.path
    ]
    for route in numeric:
        copy = _NonNumericIdRoute(
            _INT_PARAM.sub(r'{\1}', route.path),
            route.endpoint,
            methods=route.methods,
        )
        copy.fixed_routes = fixed
        app.router.routes.append(copy)


class Application:
    """The WSGI application: the FastAPI application behind a bridge."""

    def __init__(self, fastapi_app):
        self.fastapi_app = fastapi_app
        self._wsgi = ASGIMiddleware(fastapi_app)

    @property
    def registry(self):
        """The settings and configuration (queue_config...)."""
        return self.fastapi_app.state.registry

    def __call__(self, environ, start_response):
        return self._wsgi(environ, start_response)
