from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from c2corg_api.models import Base, schema


class AvalancheBulletin(Base):
    """A CAAML v6 bulletin of an avalanche service, as harvested."""

    # One row by publication and language: a row is never updated. The
    # publications superseded the same day are pruned after a week (see
    # avalanche_bulletins.store.prune_superseded).

    __tablename__ = 'avalanche_bulletins'

    id = Column(BigInteger, primary_key=True)
    # 'meteofrance', or the id of the EAWS service ('CH', 'IT-23')
    provider = Column(Text, nullable=False)
    bulletin_id = Column(Text, nullable=False)
    lang = Column(Text, nullable=False)
    publication_time = Column(DateTime(timezone=True), nullable=False)
    valid_start = Column(DateTime(timezone=True), nullable=False)
    valid_end = Column(DateTime(timezone=True), nullable=False)
    # the day it is valid for (cache.main_date)
    main_date = Column(Date, nullable=False)
    region_ids = Column(ARRAY(Text), nullable=False)
    caaml = Column(JSONB, nullable=False)
    source_id = Column(
        Text, ForeignKey(schema + '.harvest_sources.id', ondelete='SET NULL')
    )

    __table_args__ = (
        UniqueConstraint(
            'provider',
            'bulletin_id',
            'lang',
            'publication_time',
            name='uq_avalanche_bulletins_publication',
        ),
        Index(
            'ix_guidebook_avalanche_bulletins_region_ids',
            'region_ids',
            postgresql_using='gin',
        ),
        Index('ix_guidebook_avalanche_bulletins_main_date', 'main_date'),
        {'schema': schema},
    )


class AvalancheBulletinRegion(Base):
    """The danger of a region on a day, from its latest bulletin of the day."""

    # Kept forever, for the history of the danger (a few hundreds of rows a
    # day). The ratings from 1 (low) to 5 (very high), null without one.

    __tablename__ = 'avalanche_bulletin_regions'

    region_id = Column(Text, primary_key=True)
    main_date = Column(Date, primary_key=True)
    bulletin = Column(
        BigInteger,
        ForeignKey(schema + '.avalanche_bulletins.id', ondelete='SET NULL'),
    )
    max_rating = Column(SmallInteger)
    # below and above elevation_bound (meters or 'treeline'), both the
    # rating of the day without a bound
    rating_low = Column(SmallInteger)
    rating_high = Column(SmallInteger)
    elevation_bound = Column(Text)
    problems = Column(ARRAY(Text), nullable=False)
    aspects = Column(ARRAY(Text), nullable=False)
    publication_time = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = ({'schema': schema},)
