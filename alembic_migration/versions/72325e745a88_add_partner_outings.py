"""Add the tables of the partner outings.

Revision ID: 72325e745a88
Revises: 97e65791be32
Create Date: 2026-11-24 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '72325e745a88'
down_revision = '97e65791be32'
branch_labels = None
depends_on = None

# PostgreSQL 9.6 in production: plain DDL only. The enum types exist already.


def _enum_array(name):
    return postgresql.ARRAY(
        postgresql.ENUM(name=name, schema='guidebook', create_type=False)
    )


def upgrade():
    op.create_table(
        'partner_outings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('author_url', sa.String(length=500), nullable=True),
        sa.Column('region', sa.String(length=200), nullable=True),
        sa.Column('activities', _enum_array('activity_type'), nullable=False),
        sa.Column('source_activity', sa.String(length=32), nullable=True),
        sa.Column(
            'ski_rating_min',
            postgresql.ENUM(name='ski_rating', schema='guidebook', create_type=False),
            nullable=True,
        ),
        sa.Column(
            'ski_rating_max',
            postgresql.ENUM(name='ski_rating', schema='guidebook', create_type=False),
            nullable=True,
        ),
        sa.Column('rating_raw', sa.String(length=32), nullable=True),
        sa.Column('rating_system', sa.String(length=16), nullable=True),
        sa.Column(
            'steep', sa.Boolean(), server_default=sa.text('false'), nullable=False
        ),
        sa.Column('elevation_max', sa.SmallInteger(), nullable=True),
        sa.Column('height_diff_up', sa.SmallInteger(), nullable=True),
        sa.Column('orientations', _enum_array('orientation_type'), nullable=True),
        sa.Column('snow', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'geom',
            Geometry(geometry_type='POINT', srid=3857, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            'geom_quality', sa.String(length=16), server_default='none', nullable=False
        ),
        sa.Column(
            'area_ids',
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            'first_seen_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'fetched_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source', 'external_id', name='uq_partner_outings_source_external_id'
        ),
        sa.CheckConstraint(
            "geom_quality IN ('summit', 'start', 'route', 'area_centroid', 'none')",
            name='partner_outings_geom_quality_check',
        ),
        schema='guidebook',
    )
    op.execute(
        'CREATE INDEX partner_outings_date_idx ON guidebook.partner_outings (date DESC)'
    )
    op.execute(
        'CREATE INDEX partner_outings_geom_idx '
        'ON guidebook.partner_outings USING gist (geom)'
    )
    op.execute(
        'CREATE INDEX partner_outings_area_ids_idx '
        'ON guidebook.partner_outings USING gin (area_ids)'
    )
    # No GIN index on `activities`: PostgreSQL 9.6 (production) has no default GIN
    # operator class for enum arrays. The 31-day retention keeps date scans small.

    op.create_table(
        'partner_sources',
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column(
            'status', sa.String(length=16), server_default='never_run', nullable=False
        ),
        sa.Column('status_detail', sa.String(length=500), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'consecutive_failures',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('last_duration_ms', sa.Integer(), nullable=True),
        sa.Column('last_requests', sa.Integer(), nullable=True),
        sa.Column('last_fetched', sa.Integer(), nullable=True),
        sa.Column('last_upserted', sa.Integer(), nullable=True),
        sa.Column(
            'last_skipped',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('cursor', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('source'),
        sa.CheckConstraint(
            "status IN ('never_run', 'ok', 'degraded', 'blocked', 'down', "
            "'failing', 'disabled')",
            name='partner_sources_status_check',
        ),
        schema='guidebook',
    )

    op.create_table(
        'partner_lookups',
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'fetched_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('source', 'key'),
        schema='guidebook',
    )


def downgrade():
    # the indexes go with the table
    op.drop_table('partner_lookups', schema='guidebook')
    op.drop_table('partner_sources', schema='guidebook')
    op.drop_table('partner_outings', schema='guidebook')
