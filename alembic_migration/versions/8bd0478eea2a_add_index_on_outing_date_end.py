"""Add index on outing date_end

Revision ID: 8bd0478eea2a
Revises: 91b1beed9a1c
Create Date: 2017-05-08 19:43:33.817581

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '8bd0478eea2a'
down_revision = '91b1beed9a1c'
branch_labels = None
depends_on = None

def upgrade():
    op.create_index(
        'outing_date_end_idx', 'outings', ['date_end'], schema='guidebook')


def downgrade():
    op.drop_index('outing_date_end_idx', 'outings', schema='guidebook')
