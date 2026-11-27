"""Partner outings: the gpx_url and the texts of an outing.

`gpx_url`: the link to the public GPX file of a partner report (gulliver.it:
the first track of the report). Only the URL is stored here.
`texts`: the free texts of the report (narrative, conditions...), plain text
keyed by kind. Stored for later use, never served by the API.

Revision ID: c5e8a1f0d2b7
Revises: b8d2f4a61c3e
Create Date: 2026-11-27 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c5e8a1f0d2b7'
down_revision = 'b8d2f4a61c3e'
branch_labels = None
depends_on = None


def upgrade():
    # nullable, no default: instant on PostgreSQL 9.6
    op.add_column(
        'partner_outings',
        sa.Column('gpx_url', sa.String(500), nullable=True),
        schema='guidebook',
    )
    op.add_column(
        'partner_outings',
        sa.Column('texts', postgresql.JSONB(), nullable=True),
        schema='guidebook',
    )


def downgrade():
    op.drop_column('partner_outings', 'texts', schema='guidebook')
    op.drop_column('partner_outings', 'gpx_url', schema='guidebook')
