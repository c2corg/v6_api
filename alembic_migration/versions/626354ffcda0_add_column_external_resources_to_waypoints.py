"""add_column_external_resources_to_waypoints

Revision ID: 626354ffcda0
Revises: 305b064bdf66
Create Date: 2024-02-18 08:36:44.714268

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '626354ffcda0'
down_revision = '305b064bdf66'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'waypoints_locales',
        sa.Column(
            'external_resources',
            sa.String(),
            nullable=True),
        schema='guidebook')
    op.add_column(
        'waypoints_locales_archives',
        sa.Column(
            'external_resources',
            sa.String(),
            nullable=True),
        schema='guidebook')


def downgrade():
    op.drop_column('waypoints_locales', 'external_resources', schema='guidebook')
    op.drop_column('waypoints_locales_archives', 'external_resources', schema='guidebook')
