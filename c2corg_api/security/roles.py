import datetime
import hashlib
import logging
import secrets
from typing import NamedTuple

import jwt as pyjwt
from sqlalchemy import and_

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models import DBSession
from c2corg_api.models.token import Token
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

# The number of days after which a token is expired
CONST_EXPIRE_AFTER_DAYS = 14


class IssuedToken(NamedTuple):
    """A new token, to answer: the database only keeps its hash."""

    value: str
    expire: datetime.datetime


def hash_token(token):
    """Return the hash of a token, as the database stores it."""
    # a plain SHA-256 is enough: a token is long and random, not a password
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _stored(token):
    """Return the condition matching the stored row of a token."""
    # TODO(#2365): match the hash only, in the release after the migration
    # a7c3e1f05b2d. Until it has run, and while API servers of the previous
    # version still store tokens during the rolling upgrade, a row may hold
    # the token itself.
    return Token.value.in_([hash_token(token), token])


def is_valid_token(token):
    now = datetime.datetime.now(datetime.UTC)
    token = DBSession.query(Token).filter(_stored(token), Token.expire > now).first()

    if not token:
        return False
    else:
        user_is_blocked = (
            DBSession.query(User.blocked).filter(User.id == token.userid).scalar()
        )
        if user_is_blocked:
            raise HTTPForbidden('account blocked')
    return True


def add_token(value, expire, userid):
    """Store the hash of a new token and return the token."""
    # every token is unique (its `jti` claim), so it is never stored yet
    DBSession.add(Token(value=hash_token(value), expire=expire, userid=userid))
    DBSession.flush()
    return IssuedToken(value, expire)


def remove_token(token):
    now = datetime.datetime.now(datetime.UTC)
    condition = and_(_stored(token), Token.expire > now)
    result = DBSession.execute(Token.__table__.delete().where(condition))
    if result.rowcount == 0:
        log.debug('Failed to remove a token')
    DBSession.flush()


def create_claims(user, now, exp):
    """Return the claims of a new token of the user, issued now."""
    # jti: a random id, so that two tokens issued in the same second differ
    return {
        'sub': str(user.id),
        'username': user.username,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
        'jti': secrets.token_urlsafe(16),
    }


def try_login(user, password, request):
    if user.email_validated and user.validate_password(password):
        return log_validated_user_i_know_what_i_do(user, request)
    else:
        return None


def log_validated_user_i_know_what_i_do(user, request):
    """Thi method may only be called for validated users.

    See the try_login function for a safe version.
    """
    # an explicit check, not an assert: `python -O` would drop it
    if not user.email_validated:
        raise ValueError('the email of the user is not validated')

    if user.blocked:
        raise HTTPForbidden('account blocked')

    return _new_token(user, request)


def _new_token(user, request):
    """Issue and store a new token of the user."""
    now = datetime.datetime.now(datetime.UTC)
    exp = now + datetime.timedelta(days=CONST_EXPIRE_AFTER_DAYS)
    token = _encode(create_claims(user, now, exp), request)
    return add_token(token, exp, user.id)


def _encode(claims, request):
    """Sign the claims of a token with the key of the settings."""
    return pyjwt.encode(
        claims, key=request.registry.settings['jwt.private_key'], algorithm='HS256'
    )


def renew_token(user, request):
    """Replace the token of the request with a new one, or return None."""
    old_token = request.authorization.token

    if is_valid_token(old_token):
        # revoked, in the transaction that stores the new one
        remove_token(old_token)
        return _new_token(user, request)

    return None
