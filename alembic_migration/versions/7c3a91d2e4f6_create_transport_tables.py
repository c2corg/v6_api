"""Create public transport tables (GTFS feeds, lines and stops)

Revision ID: 7c3a91d2e4f6
Revises: 335e0bc4df28
Create Date: 2026-10-21 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7c3a91d2e4f6'
down_revision = '335e0bc4df28'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'transport_feeds',
        sa.Column('feed_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('license', sa.String(), nullable=False),
        sa.Column('attribution', sa.String(), nullable=False),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('feed_id'),
        schema='guidebook',
    )

    op.create_table(
        'transport_lines',
        sa.Column('line_id', sa.Integer(), nullable=False),
        sa.Column('feed_id', sa.String(), nullable=False),
        sa.Column('route_id', sa.String(), nullable=False),
        sa.Column('short_name', sa.String(), nullable=False),
        sa.Column('long_name', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('text_color', sa.String(), nullable=True),
        sa.Column('operator', sa.String(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column(
            'geom',
            geoalchemy2.types.Geometry(
                geometry_type='MULTILINESTRING', srid=3857, spatial_index=False
            ),
            nullable=True,
        ),
        # the line this one is a duplicate of (the same line in another
        # feed): hidden, see c2corg_api.transport.dedup
        sa.Column('duplicate_of', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ['feed_id'], ['guidebook.transport_feeds.feed_id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('line_id'),
        sa.UniqueConstraint('feed_id', 'route_id', name='uq_transport_lines_route'),
        schema='guidebook',
    )
    op.execute(
        'CREATE INDEX idx_transport_lines_geom '
        'ON guidebook.transport_lines USING gist (geom)'
    )
    op.execute(
        'CREATE INDEX idx_transport_lines_duplicate_of '
        'ON guidebook.transport_lines (duplicate_of)'
    )

    op.create_table(
        'transport_stops',
        sa.Column('stop_pk', sa.Integer(), nullable=False),
        sa.Column('feed_id', sa.String(), nullable=False),
        sa.Column('stop_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column(
            'geom',
            geoalchemy2.types.Geometry(
                geometry_type='POINT', srid=3857, spatial_index=False
            ),
            nullable=False,
        ),
        # ids of the stop, of its platforms and their codes: the Navitia ids
        # are built from them
        sa.Column(
            'ref_ids',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
        # Navitia stop areas (guidebook.stopareas) matching this stop
        sa.Column(
            'navitia_ids',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
        # the stop that is the anchor of the cluster of stops of the same place
        # (itself for an anchor), see c2corg_api.transport.dedup
        sa.Column('cluster_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ['feed_id'], ['guidebook.transport_feeds.feed_id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('stop_pk'),
        sa.UniqueConstraint('feed_id', 'stop_id', name='uq_transport_stops_stop'),
        schema='guidebook',
    )
    op.execute(
        'CREATE INDEX idx_transport_stops_geom '
        'ON guidebook.transport_stops USING gist (geom)'
    )
    op.execute(
        'CREATE INDEX idx_transport_stops_cluster_id '
        'ON guidebook.transport_stops (cluster_id)'
    )
    op.execute(
        'CREATE INDEX idx_transport_stops_navitia_ids '
        'ON guidebook.transport_stops USING gin (navitia_ids)'
    )


def downgrade():
    op.drop_table('transport_stops', schema='guidebook')
    op.drop_table('transport_lines', schema='guidebook')
    op.drop_table('transport_feeds', schema='guidebook')
