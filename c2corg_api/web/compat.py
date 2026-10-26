"""Run the Cornice validators of the Pyramid views on a FastAPI request."""
# The query string validators of views/validation.py read request.GET and
# fill request.validated and request.errors: this adapter gives them that
# interface, so the moved routes keep exactly the same checks and messages.

from c2corg_api.web.errors import error_response


class _Errors(list):
    def add(self, location, name, description):
        self.append((location, name, description))


class ValidatedRequest:
    """The part of a Pyramid request the query string validators use."""

    def __init__(self, request):
        self.GET = request.query_params
        self.params = request.query_params
        self.validated = {}
        self.errors = _Errors()


def validate_query(request, *validators):
    """Run the validators; return (validated values, error answer or None)."""
    adapted = ValidatedRequest(request)
    for validator in validators:
        validator(adapted)
    if adapted.errors:
        return adapted.validated, error_response(adapted.errors)
    return adapted.validated, None
