from c2corg_api.models.user import User
from colanderalchemy.schema import SQLAlchemySchemaNode
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
    )
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.orm import relationship
import datetime

from c2corg_api.models import Base, schema, users_schema, DBSession
from c2corg_api.models.document import Document


class Association(Base):
    """Associations between documents.
    """
    __tablename__ = 'associations'

    parent_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    parent_document = relationship(
        Document, primaryjoin=parent_document_id == Document.document_id)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)

    # TODO ?
    link_type = Column(String(2))

    __table_args__ = (
        PrimaryKeyConstraint(parent_document_id, child_document_id),
        Base.__table_args__
    )


class AssociationLog(Base):
    """Model to log when an association between documents was established or
    removed.
    """
    __tablename__ = 'association_log'

    id = Column(Integer, primary_key=True)

    parent_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    parent_document = relationship(
        Document, primaryjoin=parent_document_id == Document.document_id)

    child_document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    child_document = relationship(
        Document, primaryjoin=child_document_id == Document.document_id)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)

    is_creation = Column(Boolean, default=True, nullable=False)
    written_at = Column(
        DateTime, default=datetime.datetime.now, nullable=False)

schema_association = SQLAlchemySchemaNode(
    Association,
    # whitelisted attributes
    includes=['parent_document_id', 'child_document_id'],
    overrides={})
