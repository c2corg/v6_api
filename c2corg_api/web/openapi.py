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


# the error envelope the API answers, as Cornice did (web.errors), until the
# move to FastAPI's validation errors (#2546)
ERRORS = {
    'title': 'Errors',
    'type': 'object',
    'required': ['status', 'errors'],
    'properties': {
        'status': {'type': 'string', 'enum': ['error']},
        'errors': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'location': {
                        'type': 'string',
                        'description': '`querystring` (also for the path '
                        'parameters), `body` or `header`.',
                    },
                    'name': {
                        'type': 'string',
                        'description': 'The parameter or field, e.g. `lang` or '
                        '`locales.0.title`.',
                    },
                    'description': {'description': 'The message.'},
                },
            },
        },
    },
}
_INVALID = {
    'description': 'Invalid parameters.',
    'content': {
        'application/json': {'schema': {'$ref': '#/components/schemas/Errors'}}
    },
}
# FastAPI's validation errors, which the API does not answer
_FASTAPI_ERRORS = ('HTTPValidationError', 'ValidationError')


def error_responses(document):
    """Replace FastAPI's 422 answers with the 400 answers of the API."""
    # FastAPI describes a 422 for every operation with parameters; the API
    # answers their errors with a 400 and its envelope (web.params)
    for operations in document.get('paths', {}).values():
        for operation in operations.values():
            responses = operation.get('responses', {})
            if responses.pop('422', None) is not None:
                responses['400'] = _INVALID
    schemas = document.setdefault('components', {}).setdefault('schemas', {})
    for name in _FASTAPI_ERRORS:
        schemas.pop(name, None)
    schemas['Errors'] = ERRORS
    return document


def include(app, excluded=()):
    """Serve /openapi.json, with the described routes only."""

    def openapi():
        if app.openapi_schema is None:
            app.openapi_schema = error_responses(
                get_openapi(
                    title='camptocamp.org API',
                    version=str(app.state.settings.get('cache_version') or '0'),
                    routes=described_routes(app, excluded),
                )
            )
        return app.openapi_schema

    app.openapi = openapi
    app.openapi_url = '/openapi.json'
    app.setup()
