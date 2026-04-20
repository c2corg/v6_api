import logging
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from c2corg_api.models import Base, schema, users_schema
from c2corg_api.models.document import Document
from c2corg_api.models.user import User

log = logging.getLogger(__name__)


class DocumentTag(Base):
    """List documents that a given user has tagged (eg. routes as "todo")."""

    __tablename__ = 'documents_tags'

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id)

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=False,
        index=True,
    )
    document = relationship(Document, primaryjoin=document_id == Document.document_id)
    document_type: Mapped[str] = mapped_column(String(1), nullable=False, index=True)

    # TODO: possible additional fields
    # tag_type (default: "todo")
    # public (default: False)

    __table_args__ = (PrimaryKeyConstraint(user_id, document_id), Base.__table_args__)


class DocumentTagLog(Base):
    """Model to log when a tag was added to or removed from a document."""

    __tablename__ = 'documents_tags_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id, viewonly=True)

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=False,
        index=True,
    )
    document = relationship(Document, primaryjoin=document_id == Document.document_id)
    document_type: Mapped[str] = mapped_column(String(1), nullable=False)

    is_creation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    written_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )
