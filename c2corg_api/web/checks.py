"""The checks before the validators: content type, permission, origin."""

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.web.errors import error_response
from c2corg_api.web.request import ValidatedRequest


def validate_origin(request, **kwargs):
    """Refuse an origin the CORS policy does not allow, as Cornice."""
    # Cornice runs it as the first validator of every view: after the token,
    # the rate limiting, the content type and the permission, and its error
    # comes with those of the other validators.
    from c2corg_api.web.cors import origin_allowed

    origin = request.headers.get('Origin')
    if origin and not origin_allowed(origin):
        request.errors.add('header', 'Origin', f'{origin} not allowed')


class Refused(Exception):
    """A request refused before its parameters are checked: the answer."""

    def __init__(self, response):
        super().__init__(response.status_code)
        self.response = response


async def refused_response(request, exc: Refused):
    return exc.response


def permission_check(view_name, permission, content_types=None):
    """Return a dependency answering the 415 of Cornice or the 403 of Pyramid."""
    # a dependency runs before FastAPI checks the typed parameters: the
    # permission is checked first, as Pyramid did
    from c2corg_api.web.auth import CurrentUser, current_user

    def check(
        request: Request, user: Annotated[CurrentUser | None, Depends(current_user)]
    ):
        refused = refusal(request, user, view_name, permission, content_types)
        if refused is not None:
            raise Refused(refused)

    return check


def refusal(request, user, view_name, permission, content_types):
    """Answer the 415 or the 403 of Pyramid, or None."""
    # as Cornice: a request with another Content-Type than those of the view
    # (json_view) is refused, before the permission check; none is accepted
    if content_types is not None:
        media_type = request.headers.get('Content-Type', '').split(';')[0].strip()
        if media_type and media_type not in content_types:
            description = f'Content-Type header should be one of {content_types}'
            return error_response([('header', 'Content-Type', description)], 415)
    # the permission is checked before the validators, as Pyramid does
    if permission and not ValidatedRequest(request, user).has_permission(permission):
        # the message of Pyramid without debug_authorization (production)
        description = (
            f'Unauthorized: {view_name}__{request.method} failed permission check'
        )
        return error_response([('body', 'Forbidden', description)], 403)
    return None
