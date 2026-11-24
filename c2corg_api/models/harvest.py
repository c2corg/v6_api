from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from c2corg_api.models import Base, schema


class HarvestSource(Base):
    """A source of a harvester (c2corg_api.harvest), and when to fetch it."""

    # One row by source: 'avalanche.meteofrance:FR-03'. The rows are synced
    # from the sources of each harvester. The runner claims the due ones by
    # moving next_run_at (FOR UPDATE SKIP LOCKED): another scheduler, or a
    # crashed run, does not fetch it twice.

    __tablename__ = 'harvest_sources'

    id = Column(Text, primary_key=True)
    harvester = Column(Text, nullable=False)
    next_run_at = Column(DateTime(timezone=True), nullable=False)
    last_attempt = Column(DateTime(timezone=True))
    last_success = Column(DateTime(timezone=True))
    # the last time the content was different
    last_change = Column(DateTime(timezone=True))
    last_error = Column(Text)
    error_count = Column(Integer, nullable=False, default=0, server_default='0')

    # what the conditional GET sends back, and the hash of the last content
    etag = Column(Text)
    last_modified = Column(Text)
    content_sha256 = Column(LargeBinary)
    # what a harvester keeps between two fetches
    state = Column(JSONB)

    __table_args__ = (
        Index('ix_guidebook_harvest_sources_next_run_at', 'next_run_at'),
        {'schema': schema},
    )


class HarvestPayload(Base):
    """A content fetched from a source, gzipped, kept a while for debugging."""

    # Written only when the content changed, and pruned after RETENTION.

    __tablename__ = 'harvest_payloads'

    id = Column(BigInteger, primary_key=True)
    source_id = Column(
        Text,
        ForeignKey(schema + '.harvest_sources.id', ondelete='CASCADE'),
        nullable=False,
    )
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    sha256 = Column(LargeBinary, nullable=False, unique=True)
    content_type = Column(String(100))
    content = Column(LargeBinary, nullable=False)

    __table_args__ = (
        Index('ix_guidebook_harvest_payloads_source_id', 'source_id'),
        Index('ix_guidebook_harvest_payloads_fetched_at', 'fetched_at'),
        {'schema': schema},
    )
