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


def groupfinder(userid):
    is_admin = DBSession.query(User). \
        filter(User.id == userid and User.admin is True). \
        count() > 0
    return ['group:admins'] if is_admin else [Authenticated]


def validate_token(token):
    # FIXME: validate expiration
    return DBSession.query(Token). \
        filter(Token.value == token).count() == 1


def add_token(value, expire, userid):
    token = Token(value=value, expire=expire, userid=userid)
    DBSession.add(token)
    DBSession.flush()


def remove_token(token):
    now = datetime.datetime.utcnow()
    condition = Token.value == token and Token.expire > now
    result = DBSession.execute(Token.__table__.delete().where(condition))
    if result.rowcount == 0:
        log.debug('Failed to remove token %s' % token)
    DBSession.flush()


def try_login(username, password, request):
    user = DBSession.query(User). \
        filter(User.username == username).first()

    if username and password and user.validate_password(password, DBSession):
        policy = request.registry.queryUtility(IAuthenticationPolicy)
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(weeks=CONST_EXPIRE_AFTER_DAYS)
        token = policy.encode_jwt(request, claims={
            'sub': username,
            'userid': user.id,
            'exp': (exp - datetime.datetime(1970, 1, 1)).total_seconds()
        })
        add_token(token, exp, user.id)
        return token
