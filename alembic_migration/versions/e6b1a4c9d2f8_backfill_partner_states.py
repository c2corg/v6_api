"""TEMPORARY: the progress of the backfill of the partner outings.

One row per partner source: the cursor of the walk through its older reports.
Dropped once the history is imported (c2corg/v6_api#2763): a later migration
drops the table (see `downgrade`), nothing else depends on it.

Revision ID: e6b1a4c9d2f8
Revises: c4e2a9d7b1f3
Create Date: 2026-11-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'e6b1a4c9d2f8'
down_revision = 'c4e2a9d7b1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'backfill_partner_states',
        sa.Column('source', sa.String(32), primary_key=True),
        sa.Column('cursor', JSONB),
        sa.Column('floor', sa.Date),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('steps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('requests', sa.Integer, nullable=False, server_default='0'),
        sa.Column('fetched', sa.Integer, nullable=False, server_default='0'),
        sa.Column('upserted', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True)),
        sa.Column('last_status', sa.String(16)),
        sa.Column('last_detail', sa.String(500)),
        schema='guidebook',
    )


def downgrade():
    op.drop_table('backfill_partner_states', schema='guidebook')
