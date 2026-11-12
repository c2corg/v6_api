"""Authentication of the routes, as the Pyramid application did it."""
# Two checks (#2365):
# - TokenValidationMiddleware, as the former jwt_database_validation tween: a
#   request with an Authorization header must carry a token known to the
#   database and not expired (401 'Invalid token'), of a user who is not
#   blocked (403 'account blocked'), whatever the route;
# - current_user(), as the former JWT policy of Pyramid: the user of a valid
#   `JWT` token (its `sub` claim an integer as a string), None for an
#   anonymous one.
# Both, and the views (request.authorization), read the token with
# parse_authorization().

import datetime
from dataclasses import dataclass
from typing import NamedTuple

import jwt
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models.user import User
from c2corg_api.security.roles import is_valid_token
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response

AUTH_TYPE = 'JWT'
ALGORITHM = 'HS256'
# PyJWT refuses a token issued in the future (`iat`): accept the clock of
# another API server being a little behind the one that issued it.
CLOCK_LEEWAY = datetime.timedelta(minutes=1)


class Authorization(NamedTuple):
    """The scheme and token of an Authorization header."""

    scheme: str
    token: str


def parse_authorization(value):
    """Return the Authorization of a header value, or None without one."""
    # `<scheme> token="<token>"` or `<scheme> <token>`; the token may be empty.
    if not value:
        return None
    scheme, _, params = value.partition(' ')
    if 'token="' in params:
        # what follows the first quote, up to the next one if any
        params = params.split('"')[1]
    return Authorization(scheme, params)


def _check_token(token):
    """Return None if the token is valid, else the error answer."""
    with request_session():
        try:
            if token and is_valid_token(token):
                return None
        except HTTPForbidden as e:
            return error_response([('body', e.title, e.detail)], 403)
    return error_response([('body', 'Unauthorized', 'Invalid token')], 401)


class TokenValidationMiddleware(BaseHTTPMiddleware):
    """Reject the requests whose token is unknown, expired or blocked."""

    async def dispatch(self, request, call_next):
        authorization = parse_authorization(request.headers.get('Authorization'))
        if authorization is not None:
            # the database lookup runs in a worker thread, like the views
            error = await run_in_threadpool(_check_token, authorization.token)
            if error is not None:
                return error
        return await call_next(request)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    is_moderator: bool


def _claims(request):
    """Return the claims of the request's token ({} if none or invalid)."""
    authorization = parse_authorization(request.headers.get('Authorization'))
    if (
        authorization is None
        or authorization.scheme != AUTH_TYPE
        or not authorization.token
    ):
        return {}
    key = request.app.state.settings['jwt.private_key']
    try:
        return jwt.decode(
            authorization.token, key, algorithms=[ALGORITHM], leeway=CLOCK_LEEWAY
        )
    except jwt.InvalidTokenError:
        return {}


def current_user(request: Request):
    """Return the authenticated user of a request, or None (a dependency)."""
    sub = _claims(request).get('sub')
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except TypeError, ValueError:
        return None
    with request_session() as session:
        is_moderator = (
            session.query(User).filter(User.id == user_id, User.moderator).count() > 0
        )
    return CurrentUser(user_id, is_moderator)
