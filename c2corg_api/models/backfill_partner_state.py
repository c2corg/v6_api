"""TEMPORARY: the progress of the backfill of the partner outings.

Delete with the other `backfill_*` files, and drop the table with the migration
`backfill_partner_states` (c2corg/v6_api#2763). Not imported by
`c2corg_api.models`: only the backfill job uses it.
"""

from sqlalchemy import Column, Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from c2corg_api.models import Base, schema


class BackfillPartnerState(Base):
    """Where the backfill of a partner source is (one row per source)."""

    __tablename__ = 'backfill_partner_states'
    __table_args__ = {'schema': schema}

    source = Column(String(32), primary_key=True)
    # the position of the walk, as the backfiller returns it
    # (`{'done': true, ...}` at the end)
    cursor = Column(JSONB)
    # the date floor of the walk
    floor = Column(Date)
    finished_at = Column(DateTime(timezone=True))
    # totals since the start (or the last reset)
    steps = Column(Integer, nullable=False, server_default='0')
    requests = Column(Integer, nullable=False, server_default='0')
    fetched = Column(Integer, nullable=False, server_default='0')
    upserted = Column(Integer, nullable=False, server_default='0')
    # the last step
    last_run_at = Column(DateTime(timezone=True))
    last_status = Column(String(16))
    last_detail = Column(String(500))
