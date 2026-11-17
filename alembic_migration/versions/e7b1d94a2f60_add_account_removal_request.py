"""Add the account removal requests.

Revision ID: c4e8a2b7d913
Revises: b3d5f8a1c9e2
Create Date: 2026-11-08 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4e8a2b7d913'
down_revision = 'b3d5f8a1c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'account_removal_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('forum_id', sa.Integer(), nullable=True),
        sa.Column('user_name', sa.String(length=200), nullable=False),
        sa.Column('user_forum_username', sa.String(length=25), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('executable_after', sa.Date(), nullable=False),
        sa.Column('target_user_id', sa.Integer(), nullable=False),
        sa.Column('target_forum_id', sa.Integer(), nullable=False),
        sa.Column('forum_url', sa.String(length=500), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('requested_by', sa.Integer(), nullable=False),
        sa.Column('topoguide_validated_by', sa.Integer(), nullable=True),
        sa.Column('topoguide_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('forum_validated_by', sa.Integer(), nullable=True),
        sa.Column('forum_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='users',
    )
    op.create_index(
        'account_removal_request_open_user_id_idx',
        'account_removal_request',
        ['user_id'],
        unique=True,
        schema='users',
        postgresql_where=sa.text('done_at IS NULL'),
    )


def downgrade():
    op.drop_index(
        'account_removal_request_open_user_id_idx',
        table_name='account_removal_request',
        schema='users',
    )
    op.drop_table('account_removal_request', schema='users')
