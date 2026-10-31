"""Typed parameters of the routes, and their errors as the validators gave them."""
# A route with typed parameters lets FastAPI check them, and describe them in
# the OpenAPI document. Their errors keep the answer of the validators of
# views/validation.py: a 400 with the error envelope, the location
# `querystring` (also for the path parameters), the same names and messages
# (#2512).

from typing import Annotated

from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator, WithJsonSchema
from pydantic_core import PydanticCustomError

from c2corg_api.models.common.attributes import default_langs
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
        errors.append(('querystring', _ERROR_NAMES.get(name, name), error['msg']))
    return error_response(errors)
