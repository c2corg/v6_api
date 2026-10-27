"""Error responses in the shape the Cornice views gave them."""

from fastapi.responses import JSONResponse


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
