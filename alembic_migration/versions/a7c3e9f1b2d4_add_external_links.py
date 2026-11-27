"""Track the links to other sites in the texts of the locales.

Revision ID: a7c3e9f1b2d4
Revises: f3a8c1d6e2b7
Create Date: 2026-11-27 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c3e9f1b2d4'
down_revision = 'f3a8c1d6e2b7'
branch_labels = None
depends_on = None


def upgrade():
    # Created empty: the script rebuild_image_embeds fills it from the texts,
    # with the markdown parser of the API (not frozen into this migration).
    op.create_table(
        'external_links',
        sa.Column('document_locale_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=False),
        sa.ForeignKeyConstraint(
            ['document_locale_id'],
            ['guidebook.documents_locales.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('document_locale_id', 'url'),
        schema='guidebook',
    )
    for column in ('url', 'host', 'document_id'):
        op.create_index(
            f'ix_guidebook_external_links_{column}',
            'external_links',
            [column],
            unique=False,
            schema='guidebook',
        )


def downgrade():
    op.drop_table('external_links', schema='guidebook')
