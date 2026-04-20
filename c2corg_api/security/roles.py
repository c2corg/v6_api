"""
Authentication helpers — framework-agnostic.

All functions that touch the database accept an explicit ``session``
parameter.  Functions that need a JWT key accept ``jwt_key``.

The legacy Pyramid wrappers (``groupfinder``, ``try_login``,
``log_validated_user_i_know_what_i_do``, ``renew_token``) are kept at
the bottom of the file for backward compatibility with the Pyramid
stack and will be removed once the migration is complete.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from c2corg_api.models.token import Token
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

# Schedule expired tokens cleanup on application start
next_expire_cleanup = datetime.now(timezone.utc)

# The number of days after which a token is expired
CONST_EXPIRE_AFTER_DAYS = 14


class AccountBlockedError(Exception):
    """Raised when an operation is attempted on a blocked user account."""

    def __init__(self, message='account blocked'):
        super().__init__(message)


def extract_token_from_params(params):
    """Extract the raw JWT string from the *params* portion of the header.

    Supports both ``token="<tok>"`` and plain ``<tok>`` formats.
    This is framework-agnostic and shared by Pyramid and FastAPI.
    """
    if 'token="' in params:
        splitted = params.split('"')
        return splitted[1] if len(splitted) >= 2 else None
    return params


def extract_token(request):
    # Extract token from 'JWT token="XXX"' or 'JWT XXX'
    params = request.authorization[1]
    return extract_token_from_params(params)


def is_valid_token(token, session):
    """Check whether *token* is still valid in the database.

    Returns ``True`` if valid.
    Raises :class:`AccountBlockedError` if the user is blocked.
    Returns ``False`` otherwise.
    """
    now = datetime.now(timezone.utc)
    token = (
        session.query(Token).filter(Token.value == token, Token.expire > now).first()
    )

    if not token:
        return False
    else:
        user_is_blocked = (
            session.query(User.blocked).filter(User.id == token.userid).scalar()
        )
        if user_is_blocked:
            raise AccountBlockedError('account blocked')
    return True


def add_or_retrieve_token(value, expire, userid, session):
    """Find an existing token or create a new one.

    *session* is the SQLAlchemy session to use.
    """
    token = (
        session.query(Token)
        .filter(Token.value == value, Token.userid == userid)
        .first()
    )
    if not token:
        token = Token(value=value, expire=expire, userid=userid)
        session.add(token)
        session.flush()

    return token


def remove_token(token, session):
    """Remove *token* from the database."""
    now = datetime.now(timezone.utc)
    condition = Token.value == token and Token.expire > now
    result = session.execute(Token.__table__.delete().where(condition))
    if result.rowcount == 0:
        log.debug('Failed to remove token %s' % token)
    session.flush()


def create_claims(user, exp):
    return {'sub': str(user.id), 'username': user.username, 'exp': int(exp.timestamp())}


def try_login(user, password, *, jwt_key, session):
    """Framework-agnostic login.  Returns a Token or None."""
    if user.email_validated and user.validate_password(password):
        return log_validated_user(user, jwt_key=jwt_key, session=session)
    return None


def log_validated_user(user, *, jwt_key, session):
    """Create a JWT token for a validated (and non-blocked) user.

    Raises :class:`AccountBlockedError` if the user is blocked.
    """
    assert user.email_validated

    if user.blocked:
        raise AccountBlockedError('account blocked')

    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=CONST_EXPIRE_AFTER_DAYS)
    claims = create_claims(user, exp)
    token_value = pyjwt.encode(claims, key=jwt_key, algorithm='HS256')
    return add_or_retrieve_token(token_value, exp, user.id, session)


def renew_token(user, old_token_str, *, jwt_key, session):
    """Renew *old_token_str* and return a fresh Token, or None."""
    if is_valid_token(old_token_str, session=session):
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=CONST_EXPIRE_AFTER_DAYS)
        claims = create_claims(user, exp)
        token_value = pyjwt.encode(claims, key=jwt_key, algorithm='HS256')
        return add_or_retrieve_token(token_value, exp, user.id, session)
    return None


# ── Legacy Pyramid helpers (to be removed) ──────────────────────────


def groupfinder(userid, request):
    """Pyramid ACL groupfinder callback.  DEPRECATED — use
    ``fastapi_security.require_moderator`` instead.
    """
    from pyramid.security import Authenticated

    from c2corg_api.models import DBSession

    is_moderator = (
        DBSession.query(User).filter(User.id == userid, User.moderator).count() > 0
    )
    return ['group:moderators'] if is_moderator else [Authenticated]


def log_validated_user_i_know_what_i_do(user, request):
    """DEPRECATED Pyramid wrapper — delegates to :func:`log_validated_user`."""
    from pyramid.httpexceptions import HTTPForbidden
    from pyramid.interfaces import IAuthenticationPolicy

    from c2corg_api.models import DBSession

    policy = request.registry.queryUtility(IAuthenticationPolicy)
    try:
        return log_validated_user(user, jwt_key=policy.private_key, session=DBSession)
    except AccountBlockedError as exc:
        raise HTTPForbidden(str(exc))


def try_login_pyramid(user, password, request):
    """DEPRECATED Pyramid wrapper — delegates to :func:`try_login`."""
    from pyramid.httpexceptions import HTTPForbidden
    from pyramid.interfaces import IAuthenticationPolicy

    from c2corg_api.models import DBSession

    policy = request.registry.queryUtility(IAuthenticationPolicy)
    try:
        return try_login(user, password, jwt_key=policy.private_key, session=DBSession)
    except AccountBlockedError as exc:
        raise HTTPForbidden(str(exc))


def renew_token_pyramid(user, request):
    """DEPRECATED Pyramid wrapper — delegates to :func:`renew_token`."""
    from pyramid.interfaces import IAuthenticationPolicy

    from c2corg_api.models import DBSession

    old_token = extract_token(request)
    policy = request.registry.queryUtility(IAuthenticationPolicy)
    return renew_token(user, old_token, jwt_key=policy.private_key, session=DBSession)


def remove_token_pyramid(token):
    """DEPRECATED Pyramid wrapper — delegates to :func:`remove_token`."""
    from c2corg_api.models import DBSession

    return remove_token(token, session=DBSession)
