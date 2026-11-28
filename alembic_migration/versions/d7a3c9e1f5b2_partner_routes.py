"""Partner routes: the routes (itineraries, topos) of the partner outings.

`partner_routes` holds one row per route of a partner site that gives its
routes an identity (skitour.fr topos, gulliver.it itineraries, bivouak.net
topos, gipfelbuch.ch routes); `partner_outing_routes` links each partner outing
to the route(s) it followed. Not linked to the c2c documents.

Revision ID: d7a3c9e1f5b2
Revises: c4e2a9d7b1f3
Create Date: 2026-11-28 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision = 'd7a3c9e1f5b2'
down_revision = 'c4e2a9d7b1f3'
branch_labels = None
depends_on = None

GEOM_QUALITIES = ('summit', 'start', 'none')


def upgrade():
    op.create_table(
        'partner_routes',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('external_id', sa.String(128), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('url', sa.String(500)),
        sa.Column('summit_name', sa.String(200)),
        sa.Column('elevation_max', sa.SmallInteger),
        sa.Column(
            'geom', Geometry(geometry_type='POINT', srid=3857, spatial_index=False)
        ),
        sa.Column('geom_quality', sa.String(16), nullable=False, server_default='none'),
        sa.Column(
            'first_seen_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'fetched_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            'source', 'external_id', name='uq_partner_routes_source_external_id'
        ),
        sa.CheckConstraint(
            'geom_quality IN ({})'.format(', '.join(f"'{q}'" for q in GEOM_QUALITIES)),
            name='partner_routes_geom_quality_check',
        ),
        schema='guidebook',
    )
    op.create_table(
        'partner_outing_routes',
        sa.Column(
            'outing_id',
            sa.Integer,
            sa.ForeignKey('guidebook.partner_outings.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column(
            'route_id',
            sa.Integer,
            sa.ForeignKey('guidebook.partner_routes.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('position', sa.SmallInteger, nullable=False, server_default='0'),
        schema='guidebook',
    )
    op.create_index(
        'partner_outing_routes_route_id_idx',
        'partner_outing_routes',
        ['route_id'],
        schema='guidebook',
    )


def downgrade():
    op.drop_table('partner_outing_routes', schema='guidebook')
    op.drop_table('partner_routes', schema='guidebook')
