"""
FastAPI security dependencies.

Provides ``get_current_user`` — a Depends-injectable that extracts and
validates the JWT token from the ``Authorization`` header, checks the
token against the database (same logic as the Pyramid JWT tween), and
returns the authenticated :class:`~c2corg_api.models.user.User`.

The header format supported is::

    Authorization: JWT token="<token>"
    Authorization: JWT <token>
"""

import logging

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.rate_limiting import check_rate_limit
from c2corg_api.security.roles import (
    AccountBlockedError,
    extract_token_from_params,
    is_valid_token,
)

log = logging.getLogger(__name__)


def _get_jwt_key() -> str:
    """Return the JWT secret from the shared settings.

    During the transitional period we read it from the Pyramid settings
    that were loaded by the ``app.py`` factory and stashed on this module
    at startup.  When Pyramid is fully removed, this will be read from
    an env-var or config file directly. TODO:
    """
    return _jwt_private_key


# Module-level cache — set once by ``configure_security``.
_jwt_private_key: str = ''


def configure_security(settings: dict) -> None:
    """Called once at startup to capture the JWT key."""
    global _jwt_private_key
    _jwt_private_key = settings.get('jwt.private_key', '')


def _extract_token(request: Request) -> str | None:
    """Extract a JWT string from the Authorization header."""
    auth = request.headers.get('Authorization')
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].upper() != 'JWT':
        return None
    return extract_token_from_params(parts[1])


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency: returns the authenticated user or raises 403/401."""
    token_str = _extract_token(request)
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Authorization required'
        )

    # Decode the JWT
    try:
        payload = pyjwt.decode(token_str, key=_get_jwt_key(), algorithms=['HS256'])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Token expired'
        )
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        )

    # Database token validation — reuses the same logic as the Pyramid
    # jwt_database_validation tween via roles.is_valid_token.
    try:
        valid = is_valid_token(token_str, session=db)
    except AccountBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        )

    user_id = payload.get('sub')
    if user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
            )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        )

    # Rate-limit write requests (POST/PUT/DELETE).
    # check_rate_limit is a no-op for read methods.
    check_rate_limit(user, request, db)

    return user


def require_moderator(user: User = Depends(get_current_user)) -> User:
    """Dependency: like ``get_current_user`` but also requires moderator."""
    if not user.moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='moderator role required'
        )
    return user


def get_optional_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """Dependency: returns the authenticated user, or ``None``
    if no (valid) token is present.

    Unlike ``get_current_user`` this never raises — it silently
    returns ``None`` for unauthenticated requests, which is
    useful for endpoints that behave differently for guests
    (e.g. xreport GET hides personal fields).
    """
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
