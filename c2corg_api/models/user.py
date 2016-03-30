import bcrypt
from c2corg_common.attributes import default_langs
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.user_profile import UserProfile
from sqlalchemy import (
    Boolean,
    Column,
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
    name = Column(String(200))
    email = Column(String(200), nullable=False, unique=True)
    email_validated = Column(Boolean, nullable=False, default=False)
    moderator = Column(Boolean, nullable=False, default=False)
    validation_nonce = Column(String(200), nullable=True, unique=True)
    validation_nonce_expire = Column(DateTime, nullable=True, unique=False)
    _password = Column('password', String(255), nullable=False)

    lang = Column(
            String(2), ForeignKey(schema + '.langs.lang'),
            nullable=False, default='fr')

    def update_validation_nonce(self, days):
        now = datetime.datetime.utcnow()
        nonce = binascii.hexlify(os.urandom(32)).decode('ascii')
        self.validation_nonce = nonce
        self.validation_nonce_expire = now + datetime.timedelta(days=days)

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
        'id', 'username', 'name', 'email', 'email_validated', 'moderator'],
    overrides={
        'id': {
            'missing': None
        }
    })


schema_create_user = SQLAlchemySchemaNode(
    User,
    # whitelisted attributes
    includes=['username', 'name', 'email', 'lang'],
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
