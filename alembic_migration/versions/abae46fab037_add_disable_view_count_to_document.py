"""Add disable view count to document

Revision ID: abae46fab037
Revises: 2d710311ac56
Create Date: 2024-01-19 08:05:11.433263

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abae46fab037'
down_revision = '2d710311ac56'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'documents',
        sa.Column(
            'disable_view_count',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
        schema='guidebook')
    query = """
        UPDATE guidebook.documents
        SET disable_view_count = true;"""
    op.execute(query)

def downgrade():
    op.drop_column('documents', 'disable_view_count', schema='guidebook')
