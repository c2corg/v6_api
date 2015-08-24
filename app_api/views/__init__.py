# Validation functions


def validate_id(request):
    """Checks if a given id is an integer.
    """
    try:
        request.validated['id'] = int(request.matchdict['id'])
    except ValueError:
        request.errors.add('url', 'id', 'invalid id')
