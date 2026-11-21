import logging

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, schema, users_schema
from c2corg_api.models.common.document_types import (
    ARTICLE_TYPE,
    BOOK_TYPE,
    OUTING_TYPE,
    ROUTE_TYPE,
    WAYPOINT_TYPE,
    XREPORT_TYPE,
)
from c2corg_api.models.document import Document
from c2corg_api.models.user import User

log = logging.getLogger(__name__)

# the types of the documents a user can mark as favourite
FAVOURITE_TYPES = (
    ROUTE_TYPE,
    WAYPOINT_TYPE,
    OUTING_TYPE,
    ARTICLE_TYPE,
    BOOK_TYPE,
    XREPORT_TYPE,
)


class FavouriteFolder(Base):
    """A folder of a user to sort their favourite documents."""

    __tablename__ = 'favourite_folders'

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id, viewonly=True)

    name = Column(String(100), nullable=False)
    # the order of the folders of a user, from 0
    position = Column(Integer, nullable=False, default=0, server_default='0')
    created_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint(user_id, name), Base.__table_args__)


class Favourite(Base):
    """A document a user marked as favourite (formerly a "todo" tag)."""

    __tablename__ = 'favourites'

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id)

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=False,
        index=True,
    )
    document = relationship(Document, primaryjoin=document_id == Document.document_id)
    document_type = Column(String(1), nullable=False, index=True)

    # no folder: the favourite is in the user's main list
    folder_id = Column(
        Integer,
        ForeignKey(schema + '.favourite_folders.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (PrimaryKeyConstraint(user_id, document_id), Base.__table_args__)


class FavouriteLog(Base):
    """Model to log when a favourite was added or removed."""

    __tablename__ = 'favourites_log'

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id, viewonly=True)

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=False,
        index=True,
    )
    document = relationship(Document, primaryjoin=document_id == Document.document_id)
    document_type = Column(String(1), nullable=False)

    is_creation = Column(Boolean, default=True, nullable=False)
    written_at = Column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )
