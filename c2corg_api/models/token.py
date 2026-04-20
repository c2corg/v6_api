from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, users_schema


class Token(Base):
    """
    Class containing active authentication tokens.
    """

    __tablename__ = 'token'
    __table_args__ = {'schema': users_schema}

    value: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    expire: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=False, index=True
    )
    userid = Column(Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
