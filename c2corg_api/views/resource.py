"""The declarations of the view classes, as Cornice read them."""
# The FastAPI routes (c2corg_api/web) serve the methods of the view classes:
# `@view` keeps the arguments of a method (validators, permission, content
# type) for the route to check them; `@resource` only documents the paths of
# a class. The views still read their errors from `request.errors`.

import re


class BaseView:
    """A view class: its methods answer the requests of its routes."""

    def __init__(self, request, context=None, **kwargs):
        self.request = request
        self.context = context


def resource(**kw):
    """Declare a view class (collection_path, path): the routes are in web/."""

    def wrapper(klass):
        return klass

    return wrapper


def view(**kw):
    """Keep the arguments of a view method, read by web.documents.view_arguments."""

    def wrapper(func):
        views = getattr(func, '__views__', None)
        if views is None:
            views = []
            func.__views__ = views
        views.append(kw)
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
        # the form fields: the views have none (web.compat)
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
