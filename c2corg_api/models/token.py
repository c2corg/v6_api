from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from c2corg_api.models import Base, users_schema


class Token(Base):
    """The active authentication tokens, by their hash."""

    __tablename__ = 'token'
    __table_args__ = {'schema': users_schema}

    # the SHA-256 of the token (security.roles.hash_token), never the token:
    # a copy of the table does not give sessions away
    value = Column(String(), nullable=False, primary_key=True)
    expire = Column(DateTime(timezone=True), nullable=False, default=False, index=True)
    userid = Column(Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
