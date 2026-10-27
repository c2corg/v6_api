"""Error responses in the shape the Cornice views gave them."""

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)


def error_response(errors, status_code=400, headers=None):
    """Return {status: error, errors: [{location, name, description}]}."""
    return JSONResponse(
        {
            'status': 'error',
            'errors': [
                {'location': location, 'name': name, 'description': description}
                for location, name, description in errors
            ],
        },
        status_code=status_code,
        headers=headers,
    )


class UnexpectedErrorMiddleware(BaseHTTPMiddleware):
    """Log an unexpected error and answer 500, like views.catch_all_error_handler."""

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            log.exception(f'Unexpected error: {e}')
            return error_response(
                [('body', 'unexpected error', 'please consult the server logs')], 500
            )
