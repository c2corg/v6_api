"""Add documents tags

Revision ID: bece9007ab83
Revises: 06d2a35e39c8
Create Date: 2019-11-10 16:46:13.660416

"""
from alembic import op
from alembic_migration import extensions
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bece9007ab83'
down_revision = '06d2a35e39c8'
branch_labels = None
depends_on = None

view_users_for_routes = extensions.ReplaceableObject(
      'guidebook.users_for_routes',
      """
SELECT guidebook.documents_tags.document_id AS route_id, array_agg(guidebook.documents_tags.user_id) AS user_ids
FROM guidebook.documents_tags
GROUP BY guidebook.documents_tags.document_id;
""")

def upgrade():
    op.create_table(
        'documents_tags',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(1), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.PrimaryKeyConstraint('user_id', 'document_id'),
        schema='guidebook')
    op.create_index(
        op.f('ix_guidebook_documents_tags_user_id'), 'documents_tags',
        ['user_id'], unique=False, schema='guidebook')
    op.create_index(
        op.f('ix_guidebook_documents_tags_document_id'), 'documents_tags',
        ['document_id'], unique=False, schema='guidebook')
    op.create_index(
        op.f('ix_guidebook_documents_tags_document_type'), 'documents_tags',
        ['document_type'], unique=False, schema='guidebook')

    op.create_table(
        'documents_tags_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(1), nullable=False),
        sa.Column('is_creation', sa.Boolean(), nullable=False),
        sa.Column('written_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
        sa.ForeignKeyConstraint(['document_id'], ['guidebook.documents.document_id']),
        sa.PrimaryKeyConstraint('id'),
        schema='guidebook')
    op.create_index(
        op.f('ix_guidebook_documents_tags_log_written_at'),
        'documents_tags_log', ['written_at'], unique=False, schema='guidebook')
    # TODO add index on user_id/document_id?

    op.create_view(view_users_for_routes)


def downgrade():
    op.drop_view(view_users_for_routes)

    op.drop_index(
        op.f('ix_guidebook_documents_tags_user_id'),
        table_name='documents_tags', schema='guidebook')
    op.drop_index(
        op.f('ix_guidebook_documents_tags_document_id'),
        table_name='documents_tags', schema='guidebook')
    op.drop_index(
        op.f('ix_guidebook_documents_tags_document_type'),
        table_name='documents_tags', schema='guidebook')
    op.drop_table('documents_tags', schema='guidebook')

    op.drop_index(
        op.f('ix_guidebook_documents_tags_log_written_at'),
        table_name='documents_tags_log', schema='guidebook')
    # TODO drop index from user_id/document_id?
    op.drop_table('documents_tags_log', schema='guidebook')
