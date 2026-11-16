"""Keep the deleted documents for a while (soft delete).

Revision ID: c4e2a9d71f3b
Revises: b3d5f8a1c9e2
Create Date: 2026-11-16 15:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'c4e2a9d71f3b'
down_revision = 'b3d5f8a1c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deleted_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=1), nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=True),
        sa.Column('title', sa.String(length=150), nullable=True),
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('restored_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('restored_by', sa.Integer(), nullable=True),
        sa.Column('snapshot', JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang']),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['author_id'], ['users.user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['restored_by'], ['users.user.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        schema='guidebook',
    )
    op.create_index(
        op.f('ix_guidebook_deleted_documents_document_id'),
        'deleted_documents',
        ['document_id'],
        unique=False,
        schema='guidebook',
    )
    op.create_index(
        op.f('ix_guidebook_deleted_documents_deleted_at'),
        'deleted_documents',
        ['deleted_at'],
        unique=False,
        schema='guidebook',
    )


def downgrade():
    op.drop_table('deleted_documents', schema='guidebook')
