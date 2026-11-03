"""The checks of the write views, the errors of a request, its body."""
# The FastAPI routes (c2corg_api/web) serve the view functions: `@write`
# keeps the checks of a write view (validators, permission, content type)
# for its route; the read routes declare their checks themselves. The views
# still read their errors from `request.errors`.

import re

JSON = ['application/json']


def write(validators=(), permission=None, json=False):
    """Declare the checks of a write view, read by web.documents.handler_arguments."""
    # permission: None, 'authenticated' or 'moderator'; json: the body must
    # be JSON (a request with another Content-Type answers 415)

    def wrapper(func):
        func.checks = (list(validators), permission, JSON if json else None)
        return func

    return wrapper


class Errors(list):
    """The errors of a request, and the status of their answer."""

    # the locations of the errors, as Cornice
    LOCATIONS = ('body', 'querystring', 'url', 'header', 'path', 'cookies', 'method')

    def __init__(self, status=400):
        self.status = status
        super().__init__()

    def add(self, location, name=None, description=None, **kw):
        """Add an error: {location, name, description}."""
        if location != '' and location not in self.LOCATIONS:
            raise ValueError(f'{location!r} not in {self.LOCATIONS}')
        self.append(dict(location=location, name=name, description=description, **kw))


def extract_body(request):
    """Return the body of a request, or {} after adding why it is invalid."""
    # as cornice.validators.extract_cstruct, which gave the body to the
    # validators: a JSON body must be an object or an array
    content_type = request.content_type
    if content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
        # the form fields: the views have none (web.request)
        return dict(request.POST)
    if content_type and not re.match('^application/(.*?)json$', content_type):
        return request.body
    if not request.body:
        return {}
    try:
        body = request.json_body
    except ValueError as e:
        request.errors.add('body', '', f'Invalid JSON: {e}')
        return {}
    if not hasattr(body, 'items') and not isinstance(body, list):
        request.errors.add('body', '', 'Should be a JSON object or an array')
        return {}
    return body
