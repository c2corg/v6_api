from c2corg_api.models import Base, schema
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, CheckConstraint
from sqlalchemy.sql.sqltypes import DateTime, Integer


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
