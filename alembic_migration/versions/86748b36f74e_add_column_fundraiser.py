"""Add column fundraiser

Revision ID: 86748b36f74e
Revises: 2c90b2e5ca7e
Create Date: 2021-09-08 13:08:15.321581

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86748b36f74e'
down_revision = '2c90b2e5ca7e'
branch_labels = None
depends_on = None

def upgrade():
    column = sa.Column('fundraiser_url', sa.Unicode(256), nullable=True)

    op.add_column('areas', column, schema='guidebook')
    op.add_column('waypoints', column, schema='guidebook')
    op.add_column('routes', column, schema='guidebook')

    op.add_column('areas_archives', column, schema='guidebook')
    op.add_column('waypoints_archives', column, schema='guidebook')
    op.add_column('routes_archives', column, schema='guidebook')

def downgrade():
    op.drop_column('areas', 'fundraiser_url', schema='guidebook')
    op.drop_column('waypoints', 'fundraiser_url', schema='guidebook')
    op.drop_column('routes', 'fundraiser_url', schema='guidebook')

    op.drop_column('areas_archives', 'fundraiser_url', schema='guidebook')
    op.drop_column('waypoints_archives', 'fundraiser_url', schema='guidebook')
    op.drop_column('routes_archives', 'fundraiser_url', schema='guidebook')
