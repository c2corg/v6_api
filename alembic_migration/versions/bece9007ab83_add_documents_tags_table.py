"""Add documents_tags table

Revision ID: bece9007ab83
Revises: 06d2a35e39c8
Create Date: 2019-11-10 16:46:13.660416

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bece9007ab83'
down_revision = '06d2a35e39c8'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'documents_tags',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id'], ),
        sa.PrimaryKeyConstraint('user_id', 'document_id'),
        schema='guidebook')


def downgrade():
    op.drop_table('documents_tags', schema='guidebook')
