"""The WSGI application: FastAPI for the routes moved to it, Pyramid for the others."""
# The routes move from Pyramid to FastAPI one resource at a time (#2365).
# Meanwhile the server is unchanged (gunicorn sync workers, PasteDeploy): the
# FastAPI application runs behind an ASGI-to-WSGI bridge, and the dispatcher
# sends each request to the application that has its route.

from a2wsgi import ASGIMiddleware
from fastapi import FastAPI
from starlette.routing import Match


def create_fastapi_app(settings):
    """Return the FastAPI application, with the routes moved to it."""
    # no generated docs: the API documentation is not served (yet)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    return app


class Dispatcher:
    """WSGI application sending each request to FastAPI or to Pyramid."""

    def __init__(self, fastapi_app, pyramid_app):
        self.fastapi_app = fastapi_app
        self.pyramid_app = pyramid_app
        self._fastapi_wsgi = ASGIMiddleware(fastapi_app)

    @property
    def registry(self):
        """The Pyramid registry (settings, queue configuration...)."""
        return self.pyramid_app.registry

    def handles(self, environ):
        """Tell whether FastAPI has the route of a request (path and method)."""
        method = environ['REQUEST_METHOD']
        requested = environ.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD')
        if method == 'OPTIONS' and requested:
            # a CORS preflight goes where the request it announces will go
            method = requested
        scope = {
            'type': 'http',
            'path': environ.get('PATH_INFO') or '/',
            'root_path': '',
            'method': method,
        }
        # a partial match is the right path with another method: that method
        # may still be served by Pyramid
        return any(
            route.matches(scope)[0] == Match.FULL
            for route in self.fastapi_app.router.routes
        )

    def __call__(self, environ, start_response):
        app = self._fastapi_wsgi if self.handles(environ) else self.pyramid_app
        return app(environ, start_response)
