"""add view count to document

Revision ID: 2d710311ac56
Revises: 305b064bdf66
Create Date: 2024-01-08 13:28:50.090334

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d710311ac56'
down_revision = '305b064bdf66'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'documents',
        sa.Column(
            'view_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
        schema='guidebook')

def downgrade():
    op.drop_column('documents', 'view_count', schema='guidebook')
