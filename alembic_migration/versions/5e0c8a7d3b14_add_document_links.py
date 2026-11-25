"""Track the documents linked in the texts of the locales.

Revision ID: 5e0c8a7d3b14
Revises: d41c7e9a2b85
Create Date: 2026-11-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '5e0c8a7d3b14'
down_revision = 'd41c7e9a2b85'
branch_labels = None
depends_on = None


def upgrade():
    # Created empty: the script rebuild_image_embeds fills it from the texts,
    # with the markdown parser of the API (not frozen into this migration).
    op.create_table(
        'document_links',
        sa.Column('document_locale_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(length=20), nullable=False),
        sa.Column('is_url', sa.Boolean(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=False),
        sa.ForeignKeyConstraint(
            ['document_locale_id'],
            ['guidebook.documents_locales.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('document_locale_id', 'target_id', 'target_type'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_document_links_target_id',
        'document_links',
        ['target_id'],
        unique=False,
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_document_links_document_id',
        'document_links',
        ['document_id'],
        unique=False,
        schema='guidebook',
    )


def downgrade():
    op.drop_table('document_links', schema='guidebook')
