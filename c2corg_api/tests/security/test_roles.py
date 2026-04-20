from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from pyramid.security import Authenticated

from c2corg_api.models import DBSession
from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.security.roles import (
    AccountBlockedError,
    add_or_retrieve_token,
    create_claims,
    groupfinder,
    is_valid_token,
    log_validated_user,
    remove_token,
    renew_token,
    try_login,
)
from c2corg_api.tests import BaseTestCase, global_userids

JWT_SECRET = 'test-secret-key-for-roles'


class RolesTest(BaseTestCase):
    def test_groupfinder(self):
        assert [Authenticated] == groupfinder(global_userids['contributor'], None)
        assert ['group:moderators'] == groupfinder(global_userids['moderator'], None)


class TestIsValidToken(BaseTestCase):
    """Tests for ``is_valid_token`` with explicit session."""

    def test_valid_token(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        tok = Token(value='valid-test-tok', expire=expire, userid=user.id)
        DBSession.add(tok)
        DBSession.flush()
        assert is_valid_token('valid-test-tok', session=DBSession) is True

    def test_expired_token(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        expire = datetime.now(timezone.utc) - timedelta(days=1)
        tok = Token(value='expired-test-tok', expire=expire, userid=user.id)
        DBSession.add(tok)
        DBSession.flush()
        assert is_valid_token('expired-test-tok', session=DBSession) is False

    def test_unknown_token(self):
        assert is_valid_token('nonexistent-token', session=DBSession) is False

    def test_blocked_user_raises(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        original_blocked = user.blocked
        try:
            user.blocked = True
            DBSession.flush()
            expire = datetime.now(timezone.utc) + timedelta(days=7)
            tok = Token(value='blocked-user-tok', expire=expire, userid=user.id)
            DBSession.add(tok)
            DBSession.flush()
            with self.assertRaises(AccountBlockedError):
                is_valid_token('blocked-user-tok', session=DBSession)
        finally:
            user.blocked = original_blocked
            DBSession.flush()


class TestAddOrRetrieveToken(BaseTestCase):
    def test_creates_new_token(self):
        userid = global_userids['contributor']
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        tok = add_or_retrieve_token('new-token-123', expire, userid, session=DBSession)
        assert tok is not None
        assert tok.value == 'new-token-123'

    def test_retrieves_existing_token(self):
        userid = global_userids['contributor']
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        tok1 = add_or_retrieve_token('dup-token-456', expire, userid, session=DBSession)
        tok2 = add_or_retrieve_token('dup-token-456', expire, userid, session=DBSession)
        assert tok1.value == tok2.value


class TestRemoveToken(BaseTestCase):
    def test_remove_existing_token(self):
        userid = global_userids['contributor']
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        tok = Token(value='to-remove-tok', expire=expire, userid=userid)
        DBSession.add(tok)
        DBSession.flush()
        remove_token('to-remove-tok', session=DBSession)
        found = DBSession.query(Token).filter(Token.value == 'to-remove-tok').first()
        assert found is None

    def test_remove_nonexistent_token(self):
        remove_token('does-not-exist', session=DBSession)


class TestCreateClaims(BaseTestCase):
    def test_create_claims(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        exp = datetime.now(timezone.utc) + timedelta(days=7)
        claims = create_claims(user, exp)
        assert claims['sub'] == str(user.id)
        assert claims['username'] == user.username
        assert isinstance(claims['exp'], int)


class TestLogValidatedUser(BaseTestCase):
    def test_returns_token_for_valid_user(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        assert user.email_validated
        tok = log_validated_user(user, jwt_key=JWT_SECRET, session=DBSession)
        assert tok is not None
        assert tok.value
        payload = pyjwt.decode(tok.value, JWT_SECRET, algorithms=['HS256'])
        assert payload['sub'] == str(user.id)

    def test_blocked_user_raises(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        original_blocked = user.blocked
        try:
            user.blocked = True
            DBSession.flush()
            with self.assertRaises(AccountBlockedError):
                log_validated_user(user, jwt_key=JWT_SECRET, session=DBSession)
        finally:
            user.blocked = original_blocked
            DBSession.flush()


class TestTryLogin(BaseTestCase):
    def test_wrong_password_returns_none(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        result = try_login(
            user, 'wrong-password', jwt_key=JWT_SECRET, session=DBSession
        )
        assert result is None


class TestRenewToken(BaseTestCase):
    def test_renew_valid_token(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        tok = log_validated_user(user, jwt_key=JWT_SECRET, session=DBSession)
        old_value = tok.value
        new_tok = renew_token(user, old_value, jwt_key=JWT_SECRET, session=DBSession)
        assert new_tok is not None
        assert new_tok.value

    def test_renew_invalid_token_returns_none(self):
        user = (
            DBSession.query(User).filter(User.id == global_userids['contributor']).one()
        )
        result = renew_token(
            user, 'invalid-token', jwt_key=JWT_SECRET, session=DBSession
        )
        assert result is None
