from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
    )
from sqlalchemy.orm import relationship, backref
import datetime

from c2corg_api.models import Base, schema
from document import Document, ArchiveDocument, ArchiveDocumentLocale


class HistoryMetaData(Base):
    __tablename__ = 'history_metadata'

    id = Column(Integer, primary_key=True)
    # user_id
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
        backref=backref('versions', viewonly=True))

    culture = Column(
        String(2), ForeignKey(schema + '.cultures.culture'),
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

    history_metadata_id = Column(
        Integer, ForeignKey(schema + '.history_metadata.id'), nullable=False)
    history_metadata = relationship(
        HistoryMetaData, primaryjoin=history_metadata_id == HistoryMetaData.id)
