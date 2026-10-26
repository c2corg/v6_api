"""The WSGI application: FastAPI for the routes moved to it, Pyramid for the others."""
# The routes move from Pyramid to FastAPI one resource at a time (#2365).
# Meanwhile the server is unchanged (gunicorn sync workers, PasteDeploy): the
# FastAPI application runs behind an ASGI-to-WSGI bridge, and the dispatcher
# sends each request to the application that has its route.

from a2wsgi import ASGIMiddleware
from fastapi import FastAPI
from starlette.routing import Match

from c2corg_api.web import health
from c2corg_api.web.auth import TokenValidationMiddleware
from c2corg_api.web.cors import CorsMiddleware


def create_fastapi_app(settings):
    """Return the FastAPI application, with the routes moved to it."""
    # no generated docs: the API documentation is not served (yet)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    # the last middleware added runs first: CORS wraps the token errors
    app.add_middleware(TokenValidationMiddleware)
    app.add_middleware(CorsMiddleware)
    health.include(app)
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
        path = environ.get('PATH_INFO') or '/'
        if method == 'OPTIONS':
            # a CORS preflight goes where the request it announces will go,
            # or to FastAPI if only FastAPI knows the path (it then answers
            # that the method is not allowed)
            requested = environ.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD')
            match = self._fastapi_match(path, requested or method)
            return match == Match.FULL or (
                match == Match.PARTIAL and not self._pyramid_has(path)
            )
        # a partial match is the right path with another method: that method
        # may still be served by Pyramid
        return self._fastapi_match(path, method) == Match.FULL

    def _fastapi_match(self, path, method):
        scope = {'type': 'http', 'path': path, 'root_path': '', 'method': method}
        matches = [route.matches(scope)[0] for route in self.fastapi_app.router.routes]
        return max(matches, key=lambda m: m.value, default=Match.NONE)

    def _pyramid_has(self, path):
        mapper = getattr(self.pyramid_app, 'routes_mapper', None)
        if mapper is None:
            return True
        return any(route.match(path) is not None for route in mapper.get_routes())

    def __call__(self, environ, start_response):
        app = self._fastapi_wsgi if self.handles(environ) else self.pyramid_app
        return app(environ, start_response)
