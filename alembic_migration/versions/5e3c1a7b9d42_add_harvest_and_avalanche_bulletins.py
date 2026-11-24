"""Add the harvest sources and payloads, the avalanche bulletins, the weather.

Revision ID: 5e3c1a7b9d42
Revises: 31b82bbbcecb
Create Date: 2026-11-24 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers, used by Alembic.
revision = '5e3c1a7b9d42'
down_revision = '31b82bbbcecb'
branch_labels = None
depends_on = None


def upgrade():
    # created empty: the scheduler syncs the sources of the harvesters
    op.create_table(
        'harvest_sources',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('harvester', sa.Text(), nullable=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_attempt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_change', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_publication', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('error_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('etag', sa.Text(), nullable=True),
        sa.Column('last_modified', sa.Text(), nullable=True),
        sa.Column('content_sha256', sa.LargeBinary(), nullable=True),
        sa.Column('state', JSONB(), nullable=True),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_harvest_sources_next_run_at',
        'harvest_sources',
        ['next_run_at'],
        schema='guidebook',
    )
    op.create_table(
        'harvest_payloads',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sha256', sa.LargeBinary(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ['source_id'], ['guidebook.harvest_sources.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'sha256', name='uq_harvest_payloads_content'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_harvest_payloads_fetched_at',
        'harvest_payloads',
        ['fetched_at'],
        schema='guidebook',
    )
    op.create_table(
        'avalanche_bulletins',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('bulletin_id', sa.Text(), nullable=False),
        sa.Column('lang', sa.Text(), nullable=False),
        sa.Column('publication_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('main_date', sa.Date(), nullable=False),
        sa.Column('region_ids', ARRAY(sa.Text()), nullable=False),
        sa.Column('region_keys', ARRAY(sa.Text()), nullable=False),
        sa.Column('caaml', JSONB(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('compacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['source_id'], ['guidebook.harvest_sources.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider',
            'bulletin_id',
            'lang',
            'publication_time',
            name='uq_avalanche_bulletins_publication',
        ),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletins_region_keys',
        'avalanche_bulletins',
        ['region_keys'],
        schema='guidebook',
        postgresql_using='gin',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletins_source_id',
        'avalanche_bulletins',
        ['source_id'],
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletins_main_date',
        'avalanche_bulletins',
        ['main_date'],
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletins_not_compacted',
        'avalanche_bulletins',
        ['main_date'],
        schema='guidebook',
        postgresql_where=sa.text('compacted_at IS NULL'),
    )
    op.create_table(
        'avalanche_bulletin_regions',
        sa.Column('region_id', sa.Text(), nullable=False),
        sa.Column('main_date', sa.Date(), nullable=False),
        sa.Column('region_keys', ARRAY(sa.Text()), nullable=False),
        sa.Column('bulletin', sa.BigInteger(), nullable=True),
        sa.Column('max_rating', sa.SmallInteger(), nullable=True),
        sa.Column('rating_low', sa.SmallInteger(), nullable=True),
        sa.Column('rating_high', sa.SmallInteger(), nullable=True),
        sa.Column('elevation_bound', sa.Text(), nullable=True),
        sa.Column('bands', JSONB(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('problems', ARRAY(sa.Text()), nullable=False),
        sa.Column('aspects', ARRAY(sa.Text()), nullable=False),
        sa.Column('publication_time', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['bulletin'], ['guidebook.avalanche_bulletins.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('region_id', 'main_date'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletin_regions_region_keys',
        'avalanche_bulletin_regions',
        ['region_keys'],
        schema='guidebook',
        postgresql_using='gin',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletin_regions_bulletin',
        'avalanche_bulletin_regions',
        ['bulletin'],
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_avalanche_bulletin_regions_main_date',
        'avalanche_bulletin_regions',
        ['main_date'],
        schema='guidebook',
    )
    op.create_table(
        'region_weather_hours',
        sa.Column('region_id', sa.Text(), nullable=False),
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('temperature_c', sa.REAL(), nullable=True),
        sa.Column('temperature_elevation_m', sa.SmallInteger(), nullable=True),
        sa.Column('snowfall_limit_m', sa.SmallInteger(), nullable=True),
        sa.Column('snowfall_limit_null_reason', sa.Text(), nullable=True),
        sa.Column('is_forecast', sa.Boolean(), nullable=False),
        sa.Column('publication_time', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('region_id', 'time'),
        schema='guidebook',
    )
    op.create_table(
        'region_weather_periods',
        sa.Column('region_id', sa.Text(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('wind_speed_kmh', sa.SmallInteger(), nullable=True),
        sa.Column('wind_direction', sa.Text(), nullable=True),
        sa.Column('wind_highlight', sa.Text(), nullable=True),
        sa.Column('new_snow', JSONB(), nullable=False),
        sa.Column('is_forecast', sa.Boolean(), nullable=False),
        sa.Column('publication_time', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('region_id', 'period_start'),
        schema='guidebook',
    )


def downgrade():
    op.drop_table('region_weather_periods', schema='guidebook')
    op.drop_table('region_weather_hours', schema='guidebook')
    op.drop_table('avalanche_bulletin_regions', schema='guidebook')
    op.drop_table('avalanche_bulletins', schema='guidebook')
    op.drop_table('harvest_payloads', schema='guidebook')
    op.drop_table('harvest_sources', schema='guidebook')
