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

    # One row by publication and language, updated only when a service
    # changes a publication without changing its time. The publications
    # superseded the same day are pruned after a week (see
    # avalanche_bulletins.store.prune_superseded). The weather of SLF
    # (customData.CH.weather) is stored apart (models.region_weather).

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
    # the regions and all the regions holding them, to find the bulletins of
    # a region with the GIN index (avalanche_bulletins.store.region_keys)
    region_keys = Column(ARRAY(Text), nullable=False)
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
            'ix_guidebook_avalanche_bulletins_region_keys',
            'region_keys',
            postgresql_using='gin',
        ),
        Index('ix_guidebook_avalanche_bulletins_main_date', 'main_date'),
        Index('ix_guidebook_avalanche_bulletins_source_id', 'source_id'),
        {'schema': schema},
    )


class AvalancheBulletinRegion(Base):
    """The danger of a region on a day, from its latest bulletin of the day."""

    # Kept forever, for the history of the danger (a few hundreds of rows a
    # day). The ratings from 1 (low) to 5 (very high), null without one.

    __tablename__ = 'avalanche_bulletin_regions'

    region_id = Column(Text, primary_key=True)
    main_date = Column(Date, primary_key=True)
    # the region and the regions holding it (store.region_keys)
    region_keys = Column(ARRAY(Text), nullable=False)
    bulletin = Column(
        BigInteger,
        ForeignKey(schema + '.avalanche_bulletins.id', ondelete='SET NULL'),
    )
    max_rating = Column(SmallInteger)
    # below and above elevation_bound (meters or 'treeline') when the
    # ratings have one bound, both the rating of the day without; null with
    # more bounds: see bands
    rating_low = Column(SmallInteger)
    rating_high = Column(SmallInteger)
    elevation_bound = Column(Text)
    # all the ratings, as given: [{lower, upper, rating, period}]
    bands = Column(JSONB, nullable=False)
    problems = Column(ARRAY(Text), nullable=False)
    aspects = Column(ARRAY(Text), nullable=False)
    publication_time = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            'ix_guidebook_avalanche_bulletin_regions_region_keys',
            'region_keys',
            postgresql_using='gin',
        ),
        Index('ix_guidebook_avalanche_bulletin_regions_bulletin', 'bulletin'),
        {'schema': schema},
    )
