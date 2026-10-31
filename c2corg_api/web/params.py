"""Typed parameters of the routes, and their errors as the validators gave them."""
# A route with typed parameters lets FastAPI check them, and describe them in
# the OpenAPI document. Their errors keep the answer of the validators of
# views/validation.py: a 400 with the error envelope, the location
# `querystring` (also for the path parameters), the same names and messages
# (#2512).

from typing import Annotated, Any

from fastapi import Path
from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator, WithJsonSchema
from pydantic_core import PydanticCustomError

from c2corg_api.models.common.attributes import default_langs
from c2corg_api.views.validation import parse_datetime, parse_int_safe
from c2corg_api.web.errors import error_response


def _id(name):
    def parse(value):
        try:
            value = int(value)
        except TypeError, ValueError:
            value = -1
        if value < 0:
            raise PydanticCustomError('c2corg', f'invalid {name}')
        return value

    return parse


def _lang(value):
    if value not in default_langs:
        raise PydanticCustomError('c2corg', 'invalid lang')
    return value


def _int(name):
    def parse(value):
        try:
            return int(value)
        except TypeError, ValueError:
            raise PydanticCustomError('c2corg', f'invalid {name}') from None

    return parse


Id = Annotated[
    int, BeforeValidator(_id('id')), WithJsonSchema({'type': 'integer', 'minimum': 0})
]
VersionId = Annotated[
    int,
    BeforeValidator(_id('version_id')),
    WithJsonSchema({'type': 'integer', 'minimum': 0}),
]
Lang = Annotated[
    str,
    BeforeValidator(_lang),
    WithJsonSchema({'type': 'string', 'enum': list(default_langs)}),
]

Offset = Annotated[
    int, BeforeValidator(_int('offset')), WithJsonSchema({'type': 'integer'})
]
Limit = Annotated[
    int, BeforeValidator(_int('limit')), WithJsonSchema({'type': 'integer'})
]


def integer(name):
    """Return the type of an integer parameter, `invalid <name>` if it is not."""
    return Annotated[
        int, BeforeValidator(_int(name)), WithJsonSchema({'type': 'integer'})
    ]


def _token(parse):
    # an empty token is no token, as validate_token did
    def validator(value):
        if not value:
            return None
        parsed = parse(value)
        if parsed is None:
            raise PydanticCustomError('c2corg', 'invalid format')
        return parsed

    return validator


def _feed_token(value):
    # `{id},{date and time}`, as validate_token read it
    parts = value.split(',')
    if len(parts) == 2:
        id, time = parse_int_safe(parts[0]), parse_datetime(parts[1])
        if id is not None and time:
            return id, time
    return None


# the token of the next page of a feed, or of the document changes: an empty
# token is none; parsed by the validators of views/validation.py
FeedToken = Annotated[
    Any,
    BeforeValidator(_token(_feed_token)),
    WithJsonSchema({'type': 'string'}),
]
ChangesToken = Annotated[
    Any,
    BeforeValidator(_token(parse_int_safe)),
    WithJsonSchema({'type': 'integer'}),
]

DocumentId = Annotated[Id, Path(description='The document id.')]
PathLang = Annotated[Lang, Path(description='The language of the locale.')]

# the name of a parameter in the errors, when it is not the parameter itself
_ERROR_NAMES = {'l': 'lang', 'pl': 'lang'}


async def validation_error(request, exc: RequestValidationError):
    """Answer invalid parameters as the validators did: 400, `querystring`."""
    from c2corg_api.web.cors import origin_allowed

    errors = []
    # the origin is checked first, as Cornice did, and its error comes with
    # those of the parameters
    origin = request.headers.get('Origin')
    if origin and not origin_allowed(origin):
        errors.append(('header', 'Origin', f'{origin} not allowed'))
    for error in exc.errors():
        name = str(error['loc'][-1])
        # a required integer that is missing: `invalid <name>`, as
        # check_get_for_integer_property answered
        message = f'invalid {name}' if error['type'] == 'missing' else error['msg']
        errors.append(('querystring', _ERROR_NAMES.get(name, name), message))
    return error_response(errors)
