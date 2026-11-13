import datetime
import hashlib
import logging
import secrets
from typing import NamedTuple

import jwt as pyjwt
from sqlalchemy import and_, func

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models import DBSession
from c2corg_api.models.token import Token
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

# The number of days after which a token is expired
CONST_EXPIRE_AFTER_DAYS = 14
# the lifetime of a token: "remember me" on the login, or not
REMEMBERED_LIFETIME = datetime.timedelta(days=CONST_EXPIRE_AFTER_DAYS)
SESSION_LIFETIME = datetime.timedelta(days=1)
# how long a renewed token stays valid, for the requests already sent with it
RENEWAL_GRACE = datetime.timedelta(minutes=1)


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
    return Token.value == hash_token(token)


def is_valid_token(token):
    """Is the token stored and not expired? Raise a 403 for a blocked user."""
    # one query for the token and its user: it runs on every request with a token
    now = datetime.datetime.now(datetime.UTC)
    row = (
        DBSession.query(User.blocked)
        .join(Token, Token.userid == User.id)
        .filter(_stored(token), Token.expire > now)
        .first()
    )
    if row is None:
        return False
    if row.blocked:
        raise HTTPForbidden('account blocked')
    return True


def token_expire(token):
    """Return when a valid token expires."""
    now = datetime.datetime.now(datetime.UTC)
    return (
        DBSession.query(Token.expire)
        .filter(_stored(token), Token.expire > now)
        .scalar()
    )


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


def try_login(user, password, request, remember=True):
    if user.email_validated and user.validate_password(password):
        return log_validated_user_i_know_what_i_do(user, request, remember)
    else:
        return None


def log_validated_user_i_know_what_i_do(user, request, remember=True):
    """Thi method may only be called for validated users.

    See the try_login function for a safe version.
    """
    # an explicit check, not an assert: `python -O` would drop it
    if not user.email_validated:
        raise ValueError('the email of the user is not validated')

    if user.blocked:
        raise HTTPForbidden('account blocked')

    lifetime = REMEMBERED_LIFETIME if remember else SESSION_LIFETIME
    return _new_token(user, request, lifetime)


def _new_token(user, request, lifetime):
    """Issue and store a new token of the user."""
    now = datetime.datetime.now(datetime.UTC)
    exp = now + lifetime
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
        lifetime = _lifetime(old_token, request)
        _expire_soon(old_token)
        return _new_token(user, request, lifetime)

    return None


def _expire_soon(token):
    """Revoke a renewed token at the end of the grace period."""
    # Not at once: the requests sent with it before the client stored the new
    # one (the page loading, the other tabs) would be refused. It expires in a
    # minute, or at its own expiry if sooner.
    now = datetime.datetime.now(datetime.UTC)
    DBSession.execute(
        Token.__table__.update()
        .where(_stored(token))
        .values(expire=func.least(Token.expire, now + RENEWAL_GRACE))
    )
    DBSession.flush()


def _lifetime(token, request):
    """Return the lifetime of a valid token: remembered or not."""
    # the token was checked (signature, database); `exp` is not checked again
    # here, the row of the database says it is not expired
    claims = pyjwt.decode(
        token,
        key=request.registry.settings['jwt.private_key'],
        algorithms=['HS256'],
        options={'verify_exp': False, 'verify_iat': False},
    )
    if 'iat' not in claims:
        # issued before the lifetimes, all remembered
        return REMEMBERED_LIFETIME
    issued_for = datetime.timedelta(seconds=claims['exp'] - claims['iat'])
    # one of the two lifetimes, never another one
    return SESSION_LIFETIME if issued_for <= SESSION_LIFETIME else REMEMBERED_LIFETIME
