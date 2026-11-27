"""Partner outings: the geom_quality summit_match.

A position found by the harvest job from the summit name of an outing without
coordinates (a c2c summit of the same name), told apart from a point given by
the partner (`summit`).

Revision ID: b8d2f4a61c3e
Revises: 72325e745a88
Create Date: 2026-11-25 18:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b8d2f4a61c3e'
down_revision = '72325e745a88'
branch_labels = None
depends_on = None

# PostgreSQL 9.6 in production: plain DDL only.
NAME = 'partner_outings_geom_quality_check'
TABLE = 'partner_outings'
BEFORE = ('summit', 'start', 'route', 'area_centroid', 'none')
AFTER = ('summit', 'start', 'route', 'summit_match', 'area_centroid', 'none')


def _check(values):
    return 'geom_quality IN ({})'.format(', '.join(f"'{v}'" for v in values))


def upgrade():
    op.drop_constraint(NAME, TABLE, schema='guidebook', type_='check')
    op.create_check_constraint(NAME, TABLE, _check(AFTER), schema='guidebook')


def downgrade():
    # a guessed point is not a point the partner gave: forget it (the next
    # harvest of the old code leaves these outings without position)
    op.execute(
        "UPDATE guidebook.partner_outings SET geom_quality = 'none', geom = NULL, "
        "area_ids = '{}' WHERE geom_quality = 'summit_match'"
    )
    op.drop_constraint(NAME, TABLE, schema='guidebook', type_='check')
    op.create_check_constraint(NAME, TABLE, _check(BEFORE), schema='guidebook')
