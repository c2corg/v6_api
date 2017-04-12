from c2corg_api.models import Base, schema
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, CheckConstraint, ForeignKey
from sqlalchemy.sql.sqltypes import DateTime, Integer, String


class ESSyncStatus(Base):
    """A table with a single row that indicates the last time the
    ElasticSearch index was updated.
    """
    __tablename__ = 'es_sync_status'

    last_update = Column(DateTime(timezone=True))

    # make sure there is only one row in this table
    id = Column(Integer, primary_key=True, default=1)
    __table_args__ = (
        CheckConstraint('id = 1', name='one_row_constraint'),
        {'schema': schema}
    )


def get_status(session):
    return session.query(
            ESSyncStatus.last_update, func.now().label('date_now')). \
        filter(ESSyncStatus.id == 1).one()


def mark_as_updated(session, new_update_time):
    """To be called when ElasticSearch has been updated to store the update
    time.
    """
    session.query(ESSyncStatus).filter(ESSyncStatus.id == 1). \
        update(
            {ESSyncStatus.last_update: new_update_time},
            synchronize_session=False)


class ESDeletedDocument(Base):
    """A table listing documents that have been deleted and that should be
    removed from the ES index.
    """
    __tablename__ = 'es_deleted_documents'

    document_id = Column(Integer, primary_key=True)

    type = Column(String(1))

    deleted_at = Column(
        DateTime(timezone=True), default=func.now(), nullable=False,
        index=True)


class ESDeletedLocale(Base):
    """A table listing locales that have been deleted and that should be
    removed from the ES index.
    """
    __tablename__ = 'es_deleted_locales'

    document_id = Column(Integer, primary_key=True)

    type = Column(String(1))

    lang = Column(
        String(2), ForeignKey(schema + '.langs.lang'), primary_key=True,
        nullable=False)

    deleted_at = Column(
        DateTime(timezone=True), default=func.now(), nullable=False,
        index=True)
