from c2corg_api.models.user import User
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
    )
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql.expression import over, and_
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, DBSession, schema, users_schema
from c2corg_api.models.document import (
    Document, ArchiveDocument, ArchiveDocumentLocale, ArchiveDocumentGeometry)


class HistoryMetaData(Base):
    __tablename__ = 'history_metadata'

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False,
        index=True)
    user = relationship(
        User, primaryjoin=user_id == User.id, viewonly=True)
    comment = Column(String(200))
    written_at = Column(
        DateTime(timezone=True), default=func.now(), nullable=False,
        index=True)


class DocumentVersion(Base):
    __tablename__ = 'documents_versions'

    id = Column(Integer, primary_key=True)
    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False, index=True)
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
        Integer, ForeignKey(schema + '.history_metadata.id'), nullable=False,
        index=True)
    history_metadata = relationship(
        HistoryMetaData, primaryjoin=history_metadata_id == HistoryMetaData.id)


def get_creators(document_ids):
    """ Get the creator for the list of given document ids.
    """
    t = DBSession.query(
        ArchiveDocument.document_id.label('document_id'),
        User.id.label('user_id'),
        User.name.label('name'),
        over(
            func.rank(), partition_by=ArchiveDocument.document_id,
            order_by=HistoryMetaData.id).label('rank')). \
        select_from(ArchiveDocument). \
        join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1)). \
        join(HistoryMetaData,
             DocumentVersion.history_metadata_id == HistoryMetaData.id). \
        join(User,
             HistoryMetaData.user_id == User.id). \
        filter(ArchiveDocument.document_id.in_(document_ids)). \
        subquery('t')
    query = DBSession.query(
            t.c.document_id, t.c.user_id, t.c.name). \
        filter(t.c.rank == 1)

    return {
        document_id: {
            'name': name,
            'user_id': user_id
        } for document_id, user_id, name in query
    }


def has_been_created_by(document_id, user_id):
    """Check if passed user_id is the id of the user that has created
    the initial version of this document, whatever the language.
    """
    creators = get_creators([document_id])
    creator_info = creators.get(document_id)

    return creator_info and creator_info['user_id'] == user_id
