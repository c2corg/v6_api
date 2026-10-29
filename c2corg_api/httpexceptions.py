"""The HTTP errors and redirections the views raise or return."""
# The classes, codes and titles of pyramid.httpexceptions, which the views
# used: web.compat answers them (an error as {status, errors: [{location:
# body, name: title, description: detail}]}, a redirection with its headers).


class HTTPException(Exception):
    """An HTTP answer raised (or returned) by a view."""

    code = None
    title = None

    def __init__(self, detail=None, headers=None):
        super().__init__(detail)
        self.detail = detail
        self.headers = dict(headers or {})


class HTTPError(HTTPException):
    """An error: 4xx or 5xx."""


class HTTPRedirection(HTTPException):
    """A redirection: 3xx."""


class HTTPFound(HTTPRedirection):
    code = 302
    title = 'Found'

    def __init__(self, location, headers=None):
        super().__init__(headers=headers)
        self.location = location
        self.headers['Location'] = location


class HTTPNotModified(HTTPRedirection):
    code = 304
    title = 'Not Modified'


class HTTPBadRequest(HTTPError):
    code = 400
    title = 'Bad Request'


class HTTPUnauthorized(HTTPError):
    code = 401
    title = 'Unauthorized'


class HTTPForbidden(HTTPError):
    code = 403
    title = 'Forbidden'


class HTTPNotFound(HTTPError):
    code = 404
    title = 'Not Found'


class HTTPConflict(HTTPError):
    code = 409
    title = 'Conflict'


class HTTPTooManyRequests(HTTPError):
    code = 429
    title = 'Too Many Requests'


class HTTPInternalServerError(HTTPError):
    code = 500
    title = 'Internal Server Error'
