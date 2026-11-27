from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.utils import ArrayOfEnum

# how precisely the position of a partner outing is known: given by the partner
# (`summit`, `start`, `route`), or found by the job from the hints of an outing
# without coordinates (`summit_match`: a c2c summit of the same name;
# `area_centroid`: the centroid of its region), or unknown (`none`)
GEOM_QUALITIES = (
    'summit',
    'start',
    'route',
    'summit_match',
    'area_centroid',
    'none',
)
# health of a source, see the job harvesting the partner outings
SOURCE_STATUSES = (
    'never_run',
    'ok',
    'degraded',
    'blocked',
    'down',
    'failing',
    'disabled',
)


def _in_list(column, values):
    return '{} IN ({})'.format(column, ', '.join(f"'{v}'" for v in values))


class PartnerOuting(Base):
    """An outing reported on a partner site (skitour.fr, gulliver.it...).

    Harvested by the partner outings job, shown next to the outings of the
    topoguide. Not a document: no history, no locale, no association. Only
    the fields needed to list and link the report are kept.
    """

    __tablename__ = 'partner_outings'
    __table_args__ = (
        UniqueConstraint(
            'source', 'external_id', name='uq_partner_outings_source_external_id'
        ),
        CheckConstraint(
            _in_list('geom_quality', GEOM_QUALITIES),
            name='partner_outings_geom_quality_check',
        ),
        Index('partner_outings_date_idx', text('date DESC')),
        Index('partner_outings_geom_idx', 'geom', postgresql_using='gist'),
        Index('partner_outings_area_ids_idx', 'area_ids', postgresql_using='gin'),
        {'schema': schema},
    )

    id = Column(Integer, primary_key=True)
    # 'skitour', 'gulliver'... validated in code, not an enum
    source = Column(String(32), nullable=False)
    external_id = Column(String(64), nullable=False)
    # the report page on the partner site
    url = Column(String(500), nullable=False)
    title = Column(String(300), nullable=False)
    lang = Column(String(2))
    # the day of the outing, in the local time of the source
    date = Column(Date, nullable=False)
    author = Column(String(100))
    author_url = Column(String(500))
    # the region as the partner writes it
    region = Column(String(200))
    activities = Column(ArrayOfEnum(enums.activity_type), nullable=False)
    # the raw activity code of the partner: 'skimo', 'skisteep'...
    source_activity = Column(String(32))
    ski_rating_min = Column(enums.ski_rating)
    ski_rating_max = Column(enums.ski_rating)
    # the raw rating ('3.2', 'BSA'...) and its system ('c2c_ski', 'blachere')
    rating_raw = Column(String(32))
    rating_system = Column(String(16))
    steep = Column(Boolean, nullable=False, default=False, server_default=text('false'))
    elevation_max = Column(SmallInteger)
    height_diff_up = Column(SmallInteger)
    orientations = Column(ArrayOfEnum(enums.orientation_type))
    # small structured figures only
    snow = Column(JSONB)
    # the public GPX file of the report on the partner site; the tracks phase
    # of the job fetches it and stores its points in partner_tracks
    gpx_url = Column(String(500))
    # the free texts of the report, plain text keyed by kind ('narrative',
    # 'conditions', 'access'...: see HarvestedOuting.texts). Stored, NEVER
    # served by the API (the partners' licences forbid republishing them).
    texts = Column(JSONB)
    geom = Column(Geometry(geometry_type='POINT', srid=3857, spatial_index=False))
    geom_quality = Column(
        String(16), nullable=False, default='none', server_default='none'
    )
    # the areas (all types) containing geom
    area_ids = Column(
        ARRAY(Integer),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    first_seen_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# the state of a partner track: read (`ok`), to try again (`failed`: the site
# failed), or not usable (`invalid`: not a GPX, too big, no line; tried again
# only when the outing links to another file)
TRACK_STATUSES = ('ok', 'failed', 'invalid')


class PartnerTrack(Base):
    """The GPX track of a partner outing (its `gpx_url`), points only.

    Fetched after the outings, a few a run (jobs/partner_tracks.py). Only the
    longitude, latitude and elevation of the points are kept: no time, heart
    rate, name or author. Served by `GET /partner-outings/{id}/track`, with
    the credit and licence of the source. Deleted with its outing.
    """

    __tablename__ = 'partner_tracks'
    __table_args__ = (
        UniqueConstraint(
            'source', 'external_id', name='uq_partner_tracks_source_external_id'
        ),
        ForeignKeyConstraint(
            ['source', 'external_id'],
            [
                f'{schema}.partner_outings.source',
                f'{schema}.partner_outings.external_id',
            ],
            name='fk_partner_tracks_outing',
            ondelete='CASCADE',
        ),
        CheckConstraint(
            _in_list('status', TRACK_STATUSES), name='partner_tracks_status_check'
        ),
        {'schema': schema},
    )

    id = Column(Integer, primary_key=True)
    source = Column(String(32), nullable=False)
    external_id = Column(String(64), nullable=False)
    # the file that was read
    gpx_url = Column(String(500), nullable=False)
    status = Column(String(16), nullable=False)
    detail = Column(String(200))
    attempts = Column(Integer, nullable=False, default=0, server_default=text('0'))
    last_attempt_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True))
    # a MULTILINESTRING, EPSG:3857 (2D, as the c2c geometries)
    geom = Column(Geometry(geometry_type='GEOMETRY', srid=3857, spatial_index=False))
    point_count = Column(Integer)
    simplified = Column(
        Boolean, nullable=False, default=False, server_default=text('false')
    )


class PartnerSource(Base):
    """The health of a partner source: its last run and its cursor."""

    __tablename__ = 'partner_sources'
    __table_args__ = (
        CheckConstraint(
            _in_list('status', SOURCE_STATUSES),
            name='partner_sources_status_check',
        ),
        {'schema': schema},
    )

    source = Column(String(32), primary_key=True)
    status = Column(
        String(16), nullable=False, default='never_run', server_default='never_run'
    )
    status_detail = Column(String(500))
    last_run_at = Column(DateTime(timezone=True))
    # last run with status ok or degraded
    last_success_at = Column(DateTime(timezone=True))
    last_error_at = Column(DateTime(timezone=True))
    consecutive_failures = Column(
        Integer, nullable=False, default=0, server_default=text('0')
    )
    last_duration_ms = Column(Integer)
    last_requests = Column(Integer)
    # the items returned by the adapter
    last_fetched = Column(Integer)
    last_upserted = Column(Integer)
    # {"unmapped_activity:climb": 4, "parse_error": 1}
    last_skipped = Column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # owned by the adapter, opaque to the job
    cursor = Column(JSONB)


class PartnerLookup(Base):
    """A durable cache of the secondary fetches of a source (gulliver routes)."""

    __tablename__ = 'partner_lookups'
    __table_args__ = {'schema': schema}

    source = Column(String(32), primary_key=True)
    # 'route:57949'
    key = Column(String(128), primary_key=True)
    # the extracted fields only, never the raw payload
    data = Column(JSONB, nullable=False)
    fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
