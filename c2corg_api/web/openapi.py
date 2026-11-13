"""The OpenAPI document of the routes with typed parameters."""
# Off by default (setting `api.openapi`). Only the routes whose endpoint is
# marked `described` are in it: the others still read their parameters in
# the view classes, so FastAPI knows nothing of them (#2512).

import copy
import re
import warnings

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic.json_schema import PydanticJsonSchemaWarning, models_json_schema


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


# the error envelope the API answers, as Cornice did (web.errors): for the
# refusals (403...) and the errors of the rules of the API (#2546)
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
                        'description': '`body` or `header`.',
                    },
                    'name': {
                        'type': 'string',
                        'description': 'The field, e.g. `locales.0.title`.',
                    },
                    'description': {'description': 'The message.'},
                },
            },
        },
    },
}
# a valid body that breaks a rule of the API (an association...)
_REFUSED = {
    'description': 'Not allowed by the rules of the API.',
    'content': {
        'application/json': {'schema': {'$ref': '#/components/schemas/Errors'}}
    },
}
# an invalid body, as FastAPI answers it
_INVALID = {
    'description': 'Validation Error',
    'content': {
        'application/json': {
            'schema': {'$ref': '#/components/schemas/HTTPValidationError'}
        }
    },
}


def error_responses(document):
    """Add the error envelope of the API to the schemas."""
    # the invalid parameters are FastAPI's 422, as it describes them
    schemas = document.setdefault('components', {}).setdefault('schemas', {})
    schemas['Errors'] = ERRORS
    return document


# The answers of the document reads, partly: the fields of a document depend
# on its type (and the activities of a route or an outing), only the fields of
# every document are described, the others are left open.
_LICENSE = {
    'title': 'License',
    'type': ['object', 'null'],
    'description': 'The licence of the document, `null` for a topo map.',
    'required': ['id', 'url'],
    'properties': {
        'id': {
            'type': 'string',
            'description': 'An SPDX id (`CC-BY-SA-3.0`, `CC-BY-NC-ND-3.0`), or '
            '`copyright` for an image with all rights reserved.',
        },
        'url': {'type': 'string', 'format': 'uri', 'description': 'The licence.'},
        'attribution_url': {
            'type': 'string',
            'format': 'uri',
            'description': 'The history page of the document, which lists its '
            'contributors: the attribution the licence asks for.',
        },
    },
}
_DOCUMENT = {
    'title': 'Document',
    'type': 'object',
    'description': 'A document: the other fields depend on its type.',
    'properties': {
        'document_id': {'type': 'integer'},
        'version': {'type': 'integer'},
        'type': {'type': 'string', 'description': 'The document type, e.g. `r`.'},
        'available_langs': {'type': ['array', 'null'], 'items': {'type': 'string'}},
        'license': {'$ref': '#/components/schemas/License'},
    },
    'additionalProperties': True,
}
_DOCUMENTS = {
    'title': 'Documents',
    'type': 'object',
    'required': ['documents', 'total'],
    'properties': {
        'documents': {
            'type': 'array',
            'items': {'$ref': '#/components/schemas/Document'},
        },
        'total': {'type': 'integer'},
    },
}
_VERSION = {
    'title': 'Version',
    'type': 'object',
    'properties': {
        'document': {
            'description': 'The document of the version, `null` if masked.',
            'anyOf': [{'$ref': '#/components/schemas/Document'}, {'type': 'null'}],
        },
        'version': {'type': 'object'},
        'previous_version_id': {'type': ['integer', 'null']},
        'next_version_id': {'type': ['integer', 'null']},
    },
}
RESPONSES = {
    'License': _LICENSE,
    'Document': _DOCUMENT,
    'Documents': _DOCUMENTS,
    'Version': _VERSION,
}


def document_responses(document, routes):
    """Describe the answers of the document reads."""
    # the endpoint names its answer as `response_schema` (web.documents)
    described = [r for r in routes if getattr(r.endpoint, 'response_schema', None)]
    if described:
        document.setdefault('components', {}).setdefault('schemas', {}).update(
            RESPONSES
        )
    for route in described:
        schema = {'$ref': f'#/components/schemas/{route.endpoint.response_schema}'}
        for method in route.methods:
            operation = document['paths'][route.path_format][method.lower()]
            operation['responses']['200']['content'] = {
                'application/json': {'schema': schema}
            }
    return document


_PATH_PARAMETER = re.compile(r'{(\w+)(?::(\w+))?}')


def request_bodies(document, routes):
    """Describe the bodies of the write routes, and their path parameters."""
    # The write routes still read their body and their path parameters in
    # their view functions (web.request): their body comes from the schema of
    # their body validator, set as `body_schema` on the endpoint.
    with_body = [r for r in routes if getattr(r.endpoint, 'body_schema', None)]
    schemas = document.setdefault('components', {}).setdefault('schemas', {})
    if with_body:
        with warnings.catch_warnings():
            # the DROP default of the schemas (schemas.base) has no JSON
            # value: left out of the document, as pydantic says
            warnings.simplefilter('ignore', PydanticJsonSchemaWarning)
            keys, definitions = models_json_schema(
                [(r.endpoint.body_schema, 'validation') for r in with_body],
                ref_template='#/components/schemas/{model}',
            )
        schemas.update(definitions.get('$defs', {}))
    for route in with_body:
        schema = keys[(route.endpoint.body_schema, 'validation')]
        for method in route.methods:
            operation = document['paths'][route.path_format][method.lower()]
            operation['requestBody'] = {
                'required': True,
                'content': {'application/json': {'schema': schema}},
            }
            operation.setdefault('parameters', []).extend(
                _path_parameters(route, operation)
            )
            responses = operation['responses']
            responses['422'] = _INVALID
            responses['400'] = _REFUSED
            if route.endpoint.permission:
                responses['403'] = {
                    'description': 'Not allowed: authentication or a role '
                    f'(`{route.endpoint.permission}`) is required.',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/Errors'}
                        }
                    },
                }
    return document


def _path_parameters(route, operation):
    declared = {p['name'] for p in operation.get('parameters', [])}
    for name, convertor in _PATH_PARAMETER.findall(route.path):
        if name not in declared:
            schema = (
                {'type': 'integer', 'minimum': 0}
                if convertor == 'int'
                else {'type': 'string'}
            )
            yield {'name': name, 'in': 'path', 'required': True, 'schema': schema}


def include(app, excluded=()):
    """Serve /openapi.json, with the described routes only."""

    def openapi():
        if app.openapi_schema is None:
            routes = described_routes(app, excluded)
            app.openapi_schema = document_responses(
                request_bodies(
                    error_responses(
                        get_openapi(
                            title='camptocamp.org API',
                            version=str(app.state.settings.get('cache_version') or '0'),
                            routes=routes,
                        )
                    ),
                    routes,
                ),
                routes,
            )
        return app.openapi_schema

    app.openapi = openapi
    app.openapi_url = '/openapi.json'
    app.setup()
