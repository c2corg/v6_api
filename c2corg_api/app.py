"""The FastAPI application of the API."""
# Served by uvicorn (c2corg_api.asgi); the tests drive it through an
# ASGI-to-WSGI bridge (Application).

from contextlib import asynccontextmanager

from a2wsgi import ASGIMiddleware
from anyio import to_thread
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    misc.include(app)
    users.include(app)
    navitia.include(app)
    user_actions.include(app)
    document_actions.include(app)
    if openapi.enabled(settings):
        openapi.include(app)
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
