from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    and_,
    asc,
    func,
    over,
)
from sqlalchemy.orm import Mapped, Session, backref, mapped_column, relationship

from c2corg_api.models import Base, DBSession, schema, users_schema
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
)
from c2corg_api.models.user import User


class HistoryMetaData(Base):
    __tablename__ = 'history_metadata'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False, index=True
    )
    user = relationship(User, primaryjoin=user_id == User.id, viewonly=True)
    comment: Mapped[Optional[str]] = mapped_column(String(200))
    written_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )


class DocumentVersion(Base):
    __tablename__ = 'documents_versions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=False,
        index=True,
    )
    document = relationship(
        Document,
        primaryjoin=document_id == Document.document_id,
        backref=backref('versions', viewonly=True, order_by=id),
        sync_backref=False,
    )

    lang: Mapped[str] = mapped_column(
        String(2), ForeignKey(schema + '.langs.lang'), nullable=False
    )

    document_archive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), nullable=False
    )
    document_archive = relationship(
        ArchiveDocument, primaryjoin=document_archive_id == ArchiveDocument.id
    )

    document_locales_archive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), nullable=False
    )
    document_locales_archive = relationship(
        ArchiveDocumentLocale,
        primaryjoin=document_locales_archive_id == ArchiveDocumentLocale.id,
    )

    document_geometry_archive_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(schema + '.documents_geometries_archives.id')
    )
    document_geometry_archive = relationship(
        ArchiveDocumentGeometry,
        primaryjoin=document_geometry_archive_id == ArchiveDocumentGeometry.id,
    )

    history_metadata_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.history_metadata.id'), nullable=False, index=True
    )
    history_metadata = relationship(
        HistoryMetaData, primaryjoin=history_metadata_id == HistoryMetaData.id
    )

    masked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default='false', default=False
    )


def get_creators(document_ids, db: Session):
    """Get the creator for the list of given document ids."""
    t = (
        db.query(
            ArchiveDocument.document_id.label('document_id'),
            User.id.label('user_id'),
            User.name.label('name'),
            over(
                func.rank(),
                partition_by=ArchiveDocument.document_id,
                order_by=HistoryMetaData.id,
            ).label('rank'),
        )
        .select_from(ArchiveDocument)
        .join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1,
            ),
        )
        .join(
            HistoryMetaData, DocumentVersion.history_metadata_id == HistoryMetaData.id
        )
        .join(User, HistoryMetaData.user_id == User.id)
        .filter(ArchiveDocument.document_id.in_(document_ids))
        .subquery('t')
    )
    query = db.query(t.c.document_id, t.c.user_id, t.c.name).filter(t.c.rank == 1)

    return {
        document_id: {'name': name, 'user_id': user_id}
        for document_id, user_id, name in query
    }


def has_been_created_by(document_id, user_id, db: Session):
    """Check if passed user_id is the id of the user that has created
    the initial version of this document, whatever the language.
    """
    creators = get_creators([document_id], db=db)
    creator_info = creators.get(document_id)

    return creator_info and creator_info['user_id'] == user_id


def is_less_than_24h_old(document_id, db: Session):
    """Check that the first version of this document was created less than
    24h ago.
    """
    written_at = (
        db.query(HistoryMetaData.written_at.label('written_at'))
        .select_from(HistoryMetaData)
        .join(
            DocumentVersion, DocumentVersion.history_metadata_id == HistoryMetaData.id
        )
        .filter(DocumentVersion.document_id == document_id)
        .order_by(asc(HistoryMetaData.written_at))
        .limit(1)
        .scalar()
    )
    return datetime.now(timezone.utc) - written_at <= timedelta(hours=720)
