"""add calculated duration to archive route

Revision ID: c306e1cb9bfe
Revises: 6b40cb9c7c3d
Create Date: 2025-04-17 15:56:06.657450

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c306e1cb9bfe'
down_revision = '6b40cb9c7c3d'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('routes_archives',
        sa.Column('calculated_duration', sa.Float(), nullable=True),
        schema='guidebook'
    )


def downgrade():
    op.drop_column('routes_archives', 'calculated_duration', schema='guidebook')
