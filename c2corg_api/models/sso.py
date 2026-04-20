from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from c2corg_api.models import Base, users_schema
from c2corg_api.models.user import User


class SsoKey(Base):
    """
    Class containing API keys.
    """

    __tablename__ = 'sso_key'
    __table_args__ = {'schema': users_schema}

    domain: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    key: Mapped[str] = mapped_column(String(), nullable=False, unique=True)


class SsoExternalId(Base):
    """
    Class containing User's SSO external identifiers.
    """

    __tablename__ = 'sso_external_id'
    __table_args__ = {'schema': users_schema}

    domain = Column(
        String(),
        ForeignKey(users_schema + '.sso_key.domain'),
        nullable=False,
        primary_key=True,
    )
    external_id: Mapped[int] = mapped_column(Integer, nullable=False, primary_key=True)
    user_id = Column(Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    token: Mapped[Optional[str]] = mapped_column(String())
    expire: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user = relationship(User)
