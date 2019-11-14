import logging

from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    PrimaryKeyConstraint
    )
from sqlalchemy.orm import relationship

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
        nullable=False)
    user = relationship(
        User, primaryjoin=user_id == User.id
    )

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id
    )

    # TODO: possible additional fields
    # document_type (default: "route")
    # tag_type (default: "todo")
    # public (default: False)

    __table_args__ = (
        PrimaryKeyConstraint(user_id, document_id),
        Base.__table_args__
    )
