"""The answer of a view: what it returns, or the HTTP error it raises."""

from fastapi.responses import JSONResponse, Response

from c2corg_api.httpexceptions import HTTPError, HTTPNotModified, HTTPRedirection
from c2corg_api.models.user import AccountNotValidated
from c2corg_api.web.errors import error_response


def run_view(adapted, view):
    """Call a view, and turn the HTTP exceptions it raises into answers."""
    try:
        result = call_view(adapted, view)
    except HTTPNotModified as e:
        # only the cache headers, like the Pyramid answer
        headers = {k: v for k, v in e.headers.items() if k in ('ETag', 'Cache-Control')}
        return Response(status_code=304, headers=headers)
    except HTTPRedirection as e:
        return redirection(e)
    except HTTPError as e:
        return http_error(e)
    except AccountNotValidated as e:
        return account_not_validated(e)
    if adapted.errors:
        # as Cornice: the errors the view itself adds are the answer
        return error_response(adapted.errors, adapted.errors.status)
    return render(adapted, result)


def call_view(adapted, view):
    """Call a view, and raise the redirection it may return."""
    result = view()
    if isinstance(result, HTTPRedirection):
        # returned, not raised (the image proxy)
        raise result
    return result


def render(adapted, result):
    """Answer what a view returned."""
    if isinstance(result, Response):
        # a response of its own: the progress stream of the Navitia jobs
        return result
    headers = adapted.response.headers
    content_type = adapted.response.content_type
    if content_type is not None:
        # a string, with the content type of the Pyramid string renderer
        headers = {**headers, 'Content-Type': f'{content_type}; charset=UTF-8'}
        return Response(result, headers=headers)
    status = adapted.response.status
    if status is not None:
        # an int, or a status line ('404 Not Found') as WebOb accepts
        return JSONResponse(
            result, status_code=int(str(status).split()[0]), headers=headers
        )
    if not headers:
        return result
    return JSONResponse(result, headers=headers)


def redirection(e):
    """Answer a redirection with its status, headers and text body."""
    # the text body of WebOb, which answered the redirections of Pyramid
    body = (
        f'{e.code} {e.title}\n\nThe resource was found at {e.location}; '
        'you should be redirected automatically.\n\n'
    )
    headers = {**e.headers, 'Content-Type': 'text/plain; charset=UTF-8'}
    return Response(body, status_code=e.code, headers=headers)


def account_not_validated(e):
    """Answer like the exception view of Pyramid for AccountNotValidated."""
    # e.g. the password change of an account whose email is not validated
    return error_response(
        [{'location': 'body', 'name': 'Error', 'description': list(e.args)}]
    )


def http_error(e):
    """Answer an HTTP error as Pyramid did: its title and detail."""
    return error_response([('body', e.title, e.detail)], e.code)
