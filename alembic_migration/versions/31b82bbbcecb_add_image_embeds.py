"""Track the images embedded in the texts of the locales ([img=ID]).

Revision ID: 31b82bbbcecb
Revises: 97e65791be32
Create Date: 2026-11-24 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '31b82bbbcecb'
down_revision = '97e65791be32'
branch_labels = None
depends_on = None


def upgrade():
    # Created empty: the script rebuild_image_embeds fills it from the texts,
    # with the markdown parser of the API (not frozen into this migration).
    op.create_table(
        'image_embeds',
        sa.Column('document_locale_id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('lang', sa.String(length=2), nullable=False),
        sa.ForeignKeyConstraint(
            ['document_locale_id'],
            ['guidebook.documents_locales.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('document_locale_id', 'image_id'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_image_embeds_image_id',
        'image_embeds',
        ['image_id'],
        unique=False,
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_image_embeds_document_id',
        'image_embeds',
        ['document_id'],
        unique=False,
        schema='guidebook',
    )


def downgrade():
    op.drop_table('image_embeds', schema='guidebook')
