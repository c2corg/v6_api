"""Add index on AssociationLog

Revision ID: 85a5ed3c76a8
Revises: 83956b269661
Create Date: 2019-10-25 21:20:55.476560

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '85a5ed3c76a8'
down_revision = '83956b269661'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('association_log_child_document_id_idx',
                    'association_log', ['child_document_id'],
                    unique=False,
                    schema='guidebook')
    op.create_index('association_log_parent_document_id_idx',
                    'association_log', ['parent_document_id'],
                    unique=False,
                    schema='guidebook')
    op.create_index('association_log_user_id_idx',
                    'association_log', ['user_id'],
                    unique=False,
                    schema='guidebook')


def downgrade():
    op.drop_index('association_log_parent_document_id_idx',
                  table_name='association_log',
                  schema='guidebook')
    op.drop_index('association_log_child_document_id_idx',
                  table_name='association_log',
                  schema='guidebook')
    op.drop_index('association_log_user_id_idx',
                  table_name='association_log',
                  schema='guidebook')
