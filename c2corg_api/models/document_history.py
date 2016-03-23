from c2corg_api.models.user import User
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
    )
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql.expression import exists, and_
import datetime

from c2corg_api.models import Base, DBSession, schema, users_schema
from c2corg_api.models.document import (
    Document, ArchiveDocument, ArchiveDocumentLocale, ArchiveDocumentGeometry)


class HistoryMetaData(Base):
    __tablename__ = 'history_metadata'

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)
    comment = Column(String(200))
    written_at = Column(
        DateTime, default=datetime.datetime.now, nullable=False)


class DocumentVersion(Base):
    __tablename__ = 'documents_versions'

    id = Column(Integer, primary_key=True)
    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id,
        backref=backref(
            'versions', viewonly=True, order_by=id))

    lang = Column(
        String(2), ForeignKey(schema + '.langs.lang'),
        nullable=False)

    document_archive_id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), nullable=False)
    document_archive = relationship(
        ArchiveDocument, primaryjoin=document_archive_id == ArchiveDocument.id)

    document_locales_archive_id = Column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'),
        nullable=False)
    document_locales_archive = relationship(
        ArchiveDocumentLocale,
        primaryjoin=document_locales_archive_id == ArchiveDocumentLocale.id)

    document_geometry_archive_id = Column(
        Integer, ForeignKey(schema + '.documents_geometries_archives.id'))
    document_geometry_archive = relationship(
        ArchiveDocumentGeometry,
        primaryjoin=document_geometry_archive_id == ArchiveDocumentGeometry.id)

    history_metadata_id = Column(
        Integer, ForeignKey(schema + '.history_metadata.id'), nullable=False)
    history_metadata = relationship(
        HistoryMetaData, primaryjoin=history_metadata_id == HistoryMetaData.id)


def has_been_created_by(document_id, user_id):
    """Check if passed user_id is the id of the user that has created
    the initial version of this document, whatever the language.
    """
    return DBSession.query(
        exists().where(and_(
            ArchiveDocument.document_id == document_id,
            ArchiveDocument.version == 1,
            DocumentVersion.document_id == document_id,
            HistoryMetaData.user_id == user_id
        ))
    ).scalar()
