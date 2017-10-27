from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    String
    )
from sqlalchemy.orm import relationship

from c2corg_api.models import Base, users_schema
from c2corg_api.models.user import User


class SsoKey(Base):
    """
    Class containing API keys.
    """
    __tablename__ = 'sso_key'
    __table_args__ = {"schema": users_schema}

    domain = Column(String(), nullable=False, primary_key=True)
    key = Column(String(), nullable=False, unique=True)


class SsoExternalId(Base):
    """
    Class containing User's SSO external identifiers.
    """
    __tablename__ = 'sso_external_id'
    __table_args__ = {"schema": users_schema}

    domain = Column(String(), ForeignKey(users_schema + '.sso_key.domain'),
                    nullable=False, primary_key=True)
    external_id = Column(Integer, nullable=False, primary_key=True)
    user_id = Column(Integer, ForeignKey(users_schema + '.user.id'),
                     nullable=False)
    token = Column(String())
    expire = Column(DateTime(timezone=True))

    user = relationship(User)
