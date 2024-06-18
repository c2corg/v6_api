"""Add column for terms of service

Revision ID: 1d851410e3af
Revises: 305b064bdf66
Create Date: 2023-03-03 17:29:38.587079

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d851410e3af'
down_revision = '305b064bdf66'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'user',
        sa.Column('tos_validated', sa.DateTime(timezone=True), nullable=True),
        schema='users'
    )


def downgrade():
    op.drop_column('user', 'tos_validated', schema='users')
