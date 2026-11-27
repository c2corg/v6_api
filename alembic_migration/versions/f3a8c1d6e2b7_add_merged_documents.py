"""Keep the merges of documents for a while (undo a merge).

Also indexes the redirections (merged documents), looked up by a merge and
a deletion.

Revision ID: f3a8c1d6e2b7
Revises: 5e0c8a7d3b14
Create Date: 2026-11-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'f3a8c1d6e2b7'
down_revision = '5e0c8a7d3b14'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'merged_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_document_id', sa.Integer(), nullable=False),
        sa.Column('target_document_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=1), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=True),
        sa.Column(
            'merged_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('merged_by', sa.Integer(), nullable=True),
        sa.Column('unmerged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unmerged_by', sa.Integer(), nullable=True),
        sa.Column('snapshot', JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['merged_by'], ['users.user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['unmerged_by'], ['users.user.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        schema='guidebook',
    )
    for column in ('source_document_id', 'target_document_id', 'merged_at'):
        op.create_index(
            op.f(f'ix_guidebook_merged_documents_{column}'),
            'merged_documents',
            [column],
            unique=False,
            schema='guidebook',
        )


    for table in ('documents', 'documents_archives'):
        op.create_index(
            f'ix_guidebook_{table}_redirects_to',
            table,
            ['redirects_to'],
            unique=False,
            schema='guidebook',
            postgresql_where=sa.text('redirects_to IS NOT NULL'),
        )


def downgrade():
    for table in ('documents', 'documents_archives'):
        op.drop_index(
            f'ix_guidebook_{table}_redirects_to', table_name=table, schema='guidebook'
        )
    op.drop_table('merged_documents', schema='guidebook')
