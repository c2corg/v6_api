"""Authentication of the FastAPI routes, the same as the Pyramid one."""
# Two checks, like on the Pyramid side, so that a token works the same on
# both while the routes move (#2365):
# - TokenValidationMiddleware, like the jwt_database_validation tween: a
#   request with an Authorization header must carry a token known to the
#   database and not expired (401 'Invalid token'), of a user who is not
#   blocked (403 'account blocked'), whatever the route;
# - current_user(), like IntegerSubJWTAuthenticationPolicy and the
#   groupfinder: the user of a valid `JWT` token, None for an anonymous one.
# The token rework of the review comes at the end of the step.

from dataclasses import dataclass

import jwt
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models.user import User
from c2corg_api.security.jwt_policy import _TOKEN_RE
from c2corg_api.security.roles import is_valid_token
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response

AUTH_TYPE = 'JWT'
ALGORITHM = 'HS256'


def parse_authorization(value):
    """Split an Authorization header into (type, params), like WebOb."""
    if not value:
        return None
    auth_type, _, params = value.partition(' ')
    return auth_type, params


def extract_token(params):
    """Return the token of 'token="XXX"' or 'XXX', like roles.extract_token."""
    if 'token="' in params:
        parts = params.split('"')
        return parts[1] if len(parts) >= 2 else None
    return params


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
            token = extract_token(authorization[1])
            # the database lookup runs in a worker thread, like the views
            error = await run_in_threadpool(_check_token, token)
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
    if authorization is None or authorization[0] != AUTH_TYPE:
        return {}
    match = _TOKEN_RE.search(authorization[1])
    token = match.group(1) if match else authorization[1]
    if not token:
        return {}
    key = request.app.state.settings['jwt.private_key']
    try:
        return jwt.decode(token, key, algorithms=[ALGORITHM])
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
