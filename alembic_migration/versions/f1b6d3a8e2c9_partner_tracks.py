"""Partner tracks: the GPX tracks of partner outings.

One row per partner outing with a `gpx_url`: the points of its GPX file
(personal data dropped: no time, no heart rate, no name), or why it could not
be read (`status`, `attempts`). Deleted with its outing.

Revision ID: f1b6d3a8e2c9
Revises: c5e8a1f0d2b7
Create Date: 2026-11-27 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = 'f1b6d3a8e2c9'
down_revision = 'c5e8a1f0d2b7'
branch_labels = None
depends_on = None

STATUSES = ('ok', 'failed', 'invalid')


def upgrade():
    op.create_table(
        'partner_tracks',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('external_id', sa.String(64), nullable=False),
        # the file that was read (the outing may link to another one later)
        sa.Column('gpx_url', sa.String(500), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('detail', sa.String(200)),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True)),
        sa.Column(
            'geom',
            Geometry(geometry_type='GEOMETRY', srid=3857, spatial_index=False),
        ),
        # the points of the file, and whether the line was simplified
        sa.Column('point_count', sa.Integer),
        sa.Column('simplified', sa.Boolean, nullable=False, server_default='false'),
        sa.UniqueConstraint(
            'source', 'external_id', name='uq_partner_tracks_source_external_id'
        ),
        sa.ForeignKeyConstraint(
            ['source', 'external_id'],
            ['guidebook.partner_outings.source', 'guidebook.partner_outings.external_id'],
            name='fk_partner_tracks_outing',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'status IN ({})'.format(', '.join(f"'{s}'" for s in STATUSES)),
            name='partner_tracks_status_check',
        ),
        schema='guidebook',
    )


def downgrade():
    op.drop_table('partner_tracks', schema='guidebook')
