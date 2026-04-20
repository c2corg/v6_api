from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, schema


class ESSyncStatus(Base):
    """A table with a single row that indicates the last time the
    ElasticSearch index was updated.
    """

    __tablename__ = 'es_sync_status'

    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # make sure there is only one row in this table
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    __table_args__ = (
        CheckConstraint('id = 1', name='one_row_constraint'),
        {'schema': schema},
    )


def get_status(session):
    return (
        session.query(ESSyncStatus.last_update, func.now().label('date_now'))
        .filter(ESSyncStatus.id == 1)
        .one()
    )


def mark_as_updated(session, new_update_time):
    """To be called when ElasticSearch has been updated to store the update
    time.
    """
    session.query(ESSyncStatus).filter(ESSyncStatus.id == 1).update(
        {ESSyncStatus.last_update: new_update_time}, synchronize_session=False
    )


class ESDeletedDocument(Base):
    """A table listing documents that have been deleted and that should be
    removed from the ES index.
    """

    __tablename__ = 'es_deleted_documents'

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    type: Mapped[Optional[str]] = mapped_column(String(1))

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )


class ESDeletedLocale(Base):
    """A table listing locales that have been deleted and that should be
    removed from the ES index.
    """

    __tablename__ = 'es_deleted_locales'

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    type: Mapped[Optional[str]] = mapped_column(String(1))

    lang: Mapped[str] = mapped_column(
        String(2), ForeignKey(schema + '.langs.lang'), primary_key=True, nullable=False
    )

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )
