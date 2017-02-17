"""Add table es_deleted_documents

Revision ID: 8cc46db2c515
Revises: 7e32b653172f
Create Date: 2017-02-10 11:42:50.525024

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8cc46db2c515'
down_revision = '7e32b653172f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'es_deleted_documents',
        sa.Column('document_id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(1)),
        sa.Column(
            'deleted_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False, index=True),
        schema='guidebook')


def downgrade():
    op.drop_table('es_deleted_documents', schema='guidebook')
