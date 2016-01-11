from pyramid.security import Authenticated
from pyramid.interfaces import IAuthenticationPolicy

from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.models.token import Token

import datetime
import logging

log = logging.getLogger(__name__)

# Schedule expired tokens cleanup on application start
next_expire_cleanup = datetime.datetime.utcnow()

# The number of days after which a token is expired
CONST_EXPIRE_AFTER_DAYS = 14


def extract_token(request):
    # Extract XXX from 'JWT token="XXX"'
    splitted = request.authorization[1].split('"')
    return splitted[1] if len(splitted) >= 2 else None


def groupfinder(userid, request):
    is_moderator = DBSession.query(User). \
        filter(User.id == userid and User.moderator is True). \
        count() > 0
    return ['group:moderators'] if is_moderator else [Authenticated]


def is_valid_token(token):
    now = datetime.datetime.utcnow()
    return DBSession.query(Token). \
        filter(Token.value == token and Token.expire > now).count() == 1


def add_or_retrieve_token(value, expire, userid):
    token = DBSession.query(Token). \
        filter(Token.value == value and User.id == userid).first()
    if not token:
        token = Token(value=value, expire=expire, userid=userid)
        DBSession.add(token)
        DBSession.flush()

    return token


def remove_token(token):
    now = datetime.datetime.utcnow()
    condition = Token.value == token and Token.expire > now
    result = DBSession.execute(Token.__table__.delete().where(condition))
    if result.rowcount == 0:
        log.debug('Failed to remove token %s' % token)
    DBSession.flush()


def create_claims(user, exp):
    return {
        'sub': user.id,
        'username': user.username,
        'exp': int((exp - datetime.datetime(1970, 1, 1)).total_seconds())
    }


def try_login(user, password, request):
    if user.validate_password(password, DBSession):
        policy = request.registry.queryUtility(IAuthenticationPolicy)
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(days=CONST_EXPIRE_AFTER_DAYS)
        claims = create_claims(user, exp)
        token = policy.encode_jwt(request, claims=claims).decode('utf-8')
        return add_or_retrieve_token(token, exp, user.id)

    return None


def renew_token(user, request):
    old_token = extract_token(request)

    if is_valid_token(old_token):
        policy = request.registry.queryUtility(IAuthenticationPolicy)
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(days=CONST_EXPIRE_AFTER_DAYS)
        claims = create_claims(user, exp)
        token_value = policy.encode_jwt(request, claims=claims).decode('utf-8')
        return add_or_retrieve_token(token_value, exp, user.id)

    return None
