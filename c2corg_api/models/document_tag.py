import logging

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    )
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, schema, users_schema
from c2corg_api.models.document import Document
from c2corg_api.models.user import User

log = logging.getLogger(__name__)


class DocumentTag(Base):
    """List documents that a given user has tagged (eg. routes as "todo").
    """
    __tablename__ = 'documents_tags'

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'),
        nullable=False, index=True)
    user = relationship(
        User, primaryjoin=user_id == User.id
    )

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False, index=True)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id
    )
    document_type = Column(String(1), nullable=False, index=True)

    # TODO: possible additional fields
    # tag_type (default: "todo")
    # public (default: False)

    __table_args__ = (
        PrimaryKeyConstraint(user_id, document_id),
        Base.__table_args__
    )


class DocumentTagLog(Base):
    """Model to log when a tag was added to or removed from a document.
    """
    __tablename__ = 'documents_tags_log'

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False,
        index=True)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False, index=True
    )
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id)
    document_type = Column(String(1), nullable=False)

    is_creation = Column(Boolean, default=True, nullable=False)
    written_at = Column(
        DateTime(timezone=True), default=func.now(), nullable=False,
        index=True)
