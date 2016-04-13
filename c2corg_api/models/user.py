import bcrypt
from c2corg_common.attributes import default_langs
from c2corg_api.models.schema_utils import restrict_schema
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

from c2corg_api.models import Base, users_schema, schema

import colander
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql.schema import ForeignKey

import os
import binascii

import datetime


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
            "char_length(forum_username) >= 3 and forum_username !~ '[^a-zA-Z0-9]'",  # noqa
            name='forum_username_check_constraint'),
        nullable=False, unique=True
        )
    email = Column(String(200), nullable=False, unique=True)
    email_validated = Column(Boolean, nullable=False, default=False)
    email_to_validate = Column(String(200), nullable=True)
    moderator = Column(Boolean, nullable=False, default=False)
    validation_nonce = Column(String(200), nullable=True, unique=True)
    validation_nonce_expire = Column(DateTime, nullable=True, unique=False)
    _password = Column('password', String(255), nullable=False)

    lang = Column(
            String(2), ForeignKey(schema + '.langs.lang'),
            nullable=False, default='fr')

    def update_validation_nonce(self, purpose, days):
        """Generate and overwrite the nonce.
        A nonce is a random number which is used for authentication when doing
        particular actions like changing password or validating an email. It
        must have a short lifespan to avoid unused nonces to become a security
        risk."""
        now = datetime.datetime.utcnow()
        nonce = binascii.hexlify(os.urandom(32)).decode('ascii')
        self.validation_nonce = purpose + '_' + nonce
        self.validation_nonce_expire = now + datetime.timedelta(days=days)

    def validate_nonce_purpose(self, expected_purpose):
        nonce = self.validation_nonce
        prefix = expected_purpose + '_'
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

schema_association_user = restrict_schema(schema_user, [
    'id', 'username', 'name'
])
