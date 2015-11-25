from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    String
    )

from c2corg_api.models import Base, users_schema


class Token(Base):
    """
    Class containing active authentication tokens.
    """
    __tablename__ = 'token'
    __table_args__ = {"schema": users_schema}

    value = Column(String(), nullable=False, primary_key=True)
    expire = Column(DateTime, nullable=False, default=False, index=True)
    userid = Column(Integer, ForeignKey(users_schema + '.user.id'),
                    nullable=False)
