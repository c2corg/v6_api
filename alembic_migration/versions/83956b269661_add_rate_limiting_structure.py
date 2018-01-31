"""Add rate limiting structure

Revision ID: 83956b269661
Revises: 24f8da659c78
Create Date: 2018-01-12 11:54:56.294250

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '83956b269661'
down_revision = '24f8da659c78'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user', sa.Column('ratelimit_remaining', sa.Integer()), schema='users')
    op.add_column('user', sa.Column('ratelimit_reset', sa.DateTime(timezone=True)), schema='users')
    op.add_column('user', sa.Column('ratelimit_last_blocked_window', sa.DateTime(timezone=True)), schema='users')
    op.add_column(
        'user',
        sa.Column(
            'ratelimit_times', sa.Integer(), server_default='0', nullable=False),
        schema='users')
    op.add_column(
        'user',
        sa.Column(
            'robot', sa.Boolean(), server_default='false', nullable=False),
        schema='users')


def downgrade():
    op.drop_column('user', 'ratelimit_remaining', schema='users')
    op.drop_column('user', 'ratelimit_reset', schema='users')
    op.drop_column('user', 'ratelimit_last_blocked_window', schema='users')
    op.drop_column('user', 'ratelimit_times', schema='users')
    op.drop_column('user', 'robot', schema='users')
