"""add document_views table

Revision ID: 576e341ee94d
Revises: 305b064bdf66
Create Date: 2023-01-19 21:36:30.923295

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '576e341ee94d'
down_revision = '305b064bdf66'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'document_views',
        sa.Column('document_id', sa.Integer()),
        sa.Column('view_count', sa.Integer,default=0),
        sa.Column('enable_view_count', sa.Boolean, default=True),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
        sa.PrimaryKeyConstraint('document_id'),
        schema='guidebook'
    )

def downgrade():
    op.drop_table('document_views', schema='guidebook')
