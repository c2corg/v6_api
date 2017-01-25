"""Add column User.blocked

Revision ID: 7e32b653172f
Revises: 38df9393c9a9
Create Date: 2017-01-24 14:53:37.765411

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e32b653172f'
down_revision = '38df9393c9a9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column(
            'blocked', sa.Boolean(), server_default='false', nullable=False),
        schema='users')


def downgrade():
    op.drop_column('user', 'blocked', schema='users')
