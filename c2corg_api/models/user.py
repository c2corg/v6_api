import bcrypt
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_common.attributes import default_langs
from c2corg_api.models.user_profile import UserProfile
from sqlalchemy import (
    Boolean,
    Column,
    CheckConstraint,
    Integer,
    DateTime,
    String
)

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import Base, users_schema, schema, sympa_schema, enums

import colander
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import ForeignKey, Index
from sqlalchemy import event, DDL

from enum import Enum

import os
import binascii

import datetime


class AccountNotValidated(Exception):
    def __init__(self):
        Exception.__init__(self, 'Account not validated yet')


class PasswordUtil():
    """
    Utility class abstracting low-level password primitives.
    """
    @staticmethod
    def encrypt_password(plain_password):
        if isinstance(plain_password, str):
            plain_password = plain_password.encode('utf-8')
        return bcrypt.hashpw(plain_password, bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def is_password_valid(plain, encrypted):
        if isinstance(encrypted, str):
            encrypted = encrypted.encode('utf-8')
        if isinstance(plain, str):
            plain = plain.encode('utf-8')
        return bcrypt.hashpw(plain, encrypted) == encrypted


class Purpose(Enum):
    registration = 'regemail'
    new_password = 'newpass'
    change_email = 'chgemail'


class User(Base):
    """
    Class containing the users' private and authentication data.
    """
    __tablename__ = 'user'
    __table_args__ = {'schema': users_schema}

    # the user id is the same as the document id of the user profile
    id = Column(
        Integer, ForeignKey(schema + '.user_profiles.document_id'),
        primary_key=True)
    profile = relationship(
        UserProfile, primaryjoin=id == UserProfile.document_id, uselist=False,
        backref=backref('user', uselist=False))

    username = Column(String(200), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    forum_username = Column(
        String(15),
        CheckConstraint(  # do not have non alphanumeric characters
            "users.check_forum_username(forum_username)",  # noqa
            name='forum_username_check_constraint'),
        nullable=False, unique=True
        )
    email = Column(String(200), nullable=False, unique=True)
    email_validated = Column(
        Boolean, nullable=False, default=False, index=True)
    email_to_validate = Column(String(200), nullable=True)
    moderator = Column(Boolean, nullable=False, default=False)
    validation_nonce = Column(String(200), nullable=True, unique=True)
    validation_nonce_expire = Column(DateTime, nullable=True, unique=False)
    _password = Column('password', String(255), nullable=False)
    last_modified = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
        index=True)

    lang = Column(
            String(2), ForeignKey(schema + '.langs.lang'),
            nullable=False, default='fr')

    is_profile_public = Column(
        Boolean, nullable=False, default=False, server_default='FALSE')

    # the feed on the homepage for a user is filtered on this activities
    feed_filter_activities = Column(
        ArrayOfEnum(enums.activity_type), nullable=False, server_default='{}')

    # only show updates from followed users in the homepage feed
    feed_followed_only = Column(
        Boolean, server_default='FALSE', nullable=False)

    def update_validation_nonce(self, purpose, days):
        """Generate and overwrite the nonce.
        A nonce is a random number which is used for authentication when doing
        particular actions like changing password or validating an email. It
        must have a short lifespan to avoid unused nonces to become a security
        risk."""
        if purpose != Purpose.registration and not self.email_validated:
            # An account must be validated before any other action is tried.
            raise AccountNotValidated()

        now = datetime.datetime.utcnow()
        nonce = binascii.hexlify(os.urandom(32)).decode('ascii')
        self.validation_nonce = purpose.value + '_' + nonce
        self.validation_nonce_expire = now + datetime.timedelta(days=days)

    def validate_nonce_purpose(self, expected_purpose):
        nonce = self.validation_nonce
        prefix = expected_purpose.value + '_'
        return nonce is not None and nonce.startswith(prefix)

    def clear_validation_nonce(self):
        self.validation_nonce = None
        self.validation_nonce_expire = None

    def _get_password(self):
        return self._password

    def _set_password(self, password):
        self._password = PasswordUtil.encrypt_password(password)

    def validate_password(self, plain_password):
        """Check the password against existing credentials.
        """
        return PasswordUtil.is_password_valid(plain_password, self._password)

    password = property(_get_password, _set_password)


Index('ix_users_user_lower_forum_username',
      func.lower(User.forum_username),
      unique=True)


# Check forum_username validity with discourse
# https://github.com/discourse/discourse/blob/master/app/models/username_validator.rb
check_forum_username_ddl = DDL("""
CREATE OR REPLACE FUNCTION users.check_forum_username(name TEXT)
RETURNS boolean AS $$
BEGIN
  IF name = NULL THEN
    RETURN FALSE;
  END IF;

  IF char_length(name) < 3 THEN
    RETURN FALSE;
  END IF;

  IF char_length(name) > 25 THEN
    RETURN FALSE;
  END IF;

  if name ~ '[^\w.-]' THEN
    RETURN FALSE;
  END IF;

  if left(name, 1) ~ '\W' THEN
    RETURN FALSE;
  END IF;

  if right(name, 1) ~ '[^A-Za-z0-9]' THEN
    RETURN FALSE;
  END IF;

  if name ~ '[-_\.]{2,}' THEN
    RETURN FALSE;
  END IF;

  if name ~
  '\.(js|json|css|htm|html|xml|jpg|jpeg|png|gif|bmp|ico|tif|tiff|woff)$'
  THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql;
""")
event.listen(User.__table__, 'before_create', check_forum_username_ddl)


schema_user = SQLAlchemySchemaNode(
    User,
    # whitelisted attributes
    includes=[
        'id', 'username', 'forum_username', 'name', 'email', 'email_validated',
        'moderator'],
    overrides={
        'id': {
            'missing': None
        }
    })


schema_create_user = SQLAlchemySchemaNode(
    User,
    # whitelisted attributes
    includes=['username', 'forum_username', 'name', 'email', 'lang'],
    overrides={
        'email': {
            'validator': colander.Email()
        },
        'lang': {
            'validator': colander.OneOf(default_langs)
        }
    })

# Make sure that user email changes are propagated to mailing lists as well
trigger_ddl = DDL("""
CREATE OR REPLACE FUNCTION users.update_mailinglists_email() RETURNS TRIGGER AS
$BODY$
BEGIN
  UPDATE """ + sympa_schema + """.subscriber_table
  SET user_subscriber = NEW.email
  WHERE user_subscriber = OLD.email;
  RETURN null;
END;
$BODY$
language plpgsql;

CREATE TRIGGER users_email_update
AFTER UPDATE ON users.user
FOR EACH ROW
WHEN (OLD.email IS DISTINCT FROM NEW.email)
EXECUTE PROCEDURE users.update_mailinglists_email();
""")
event.listen(User.__table__, 'after_create', trigger_ddl)
