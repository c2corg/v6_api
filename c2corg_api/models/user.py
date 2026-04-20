import binascii
import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

import bcrypt
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from c2corg_api.models import Base, enums, schema, users_schema
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.field_spec import FieldSpec
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.utils import ArrayOfEnum


class AccountNotValidatedError(Exception):
    def __init__(self):
        Exception.__init__(self, 'Account not validated yet')


class PasswordUtil:
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
    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.user_profiles.document_id'), primary_key=True
    )
    profile = relationship(
        UserProfile,
        primaryjoin=id == UserProfile.document_id,
        uselist=False,
        backref=backref('user', uselist=False, cascade_backrefs=False),
    )

    username: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    forum_username: Mapped[str] = mapped_column(String(25), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    email_validated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    email_to_validate: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    moderator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_nonce: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, unique=True
    )
    validation_nonce_expire: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, unique=False
    )
    _password: Mapped[str] = mapped_column('password', String(255), nullable=False)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tos_validated: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, unique=False
    )

    lang: Mapped[str] = mapped_column(
        String(2), ForeignKey(schema + '.langs.lang'), nullable=False, default='fr'
    )

    is_profile_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='FALSE'
    )

    # the feed on the homepage for a user is filtered on these activities
    feed_filter_activities: Mapped[List[str]] = mapped_column(
        ArrayOfEnum(enums.activity_type), nullable=False, server_default='{}'
    )

    # the feed on the homepage for a user is filtered on these langs
    feed_filter_langs: Mapped[List[str]] = mapped_column(
        ArrayOfEnum(enums.lang), nullable=False, server_default='{}'
    )

    # only show updates from followed users in the homepage feed
    feed_followed_only: Mapped[bool] = mapped_column(
        Boolean, server_default='FALSE', nullable=False
    )

    ratelimit_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    ratelimit_reset: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ratelimit_last_blocked_window: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    ratelimit_times: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    robot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def update_validation_nonce(self, purpose, days):
        """Generate and overwrite the nonce.
        A nonce is a random number which is used for authentication when doing
        particular actions like changing password or validating an email. It
        must have a short lifespan to avoid unused nonces to become a security
        risk."""
        if purpose != Purpose.registration and not self.email_validated:
            # An account must be validated before any other action is tried.
            raise AccountNotValidatedError()

        now = datetime.now(timezone.utc)
        nonce = binascii.hexlify(os.urandom(32)).decode('ascii')
        self.validation_nonce = purpose.value + '_' + nonce
        self.validation_nonce_expire = now + timedelta(days=days)

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
        """Check the password against existing credentials."""
        return PasswordUtil.is_password_valid(plain_password, self._password)

    password = property(_get_password, _set_password)


Index(
    'ix_users_user_lower_forum_username', func.lower(User.forum_username), unique=True
)


schema_user = FieldSpec(
    sa_model=User,
    columns=[
        'id',
        'username',
        'forum_username',
        'name',
        'email',
        'email_validated',
        'moderator',
    ],
)


# ===================================================================
# Pydantic schemas (for body validation in views)
# ===================================================================


class CreateUserSchema(BaseModel):
    username: str
    forum_username: str
    name: str
    email: EmailStr
    lang: Optional[DefaultLangs] = DefaultLangs.fr

    model_config = {'extra': 'ignore'}


class LoginSchema(BaseModel):
    """Pydantic ``LoginSchema``."""

    username: str
    password: str
    accept_tos: Optional[bool] = False

    model_config = {'extra': 'ignore'}
