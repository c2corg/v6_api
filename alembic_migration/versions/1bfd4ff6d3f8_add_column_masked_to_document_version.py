"""Add column masked to document version

Revision ID: 1bfd4ff6d3f8
Revises: 2c90b2e5ca7e
Create Date: 2022-10-01 20:43:49.170890

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1bfd4ff6d3f8'
down_revision = '2c90b2e5ca7e'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'documents_versions',
        sa.Column(
            'masked',
            sa.Boolean(),
            server_default='false',
            nullable=False),
        schema='guidebook')


def downgrade():
    op.drop_column('documents_versions', 'masked', schema='guidebook')
