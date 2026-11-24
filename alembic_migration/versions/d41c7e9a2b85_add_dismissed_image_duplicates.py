"""Add the pairs of images a moderator told are not duplicates.

Revision ID: d41c7e9a2b85
Revises: 31b82bbbcecb
Create Date: 2026-11-24 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd41c7e9a2b85'
down_revision = '31b82bbbcecb'
branch_labels = None
depends_on = None

# PostgreSQL 9.6 in production: a plain table.


def upgrade():
    op.create_table(
        'dismissed_image_duplicates',
        sa.Column('image1_id', sa.Integer(), nullable=False),
        sa.Column('image2_id', sa.Integer(), nullable=False),
        sa.Column('dismissed_by', sa.Integer(), nullable=True),
        sa.Column(
            'dismissed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'image1_id < image2_id', name='dismissed_image_duplicates_ordered'
        ),
        sa.ForeignKeyConstraint(
            ['image1_id'], ['guidebook.documents.document_id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['image2_id'], ['guidebook.documents.document_id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['dismissed_by'], ['users.user.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('image1_id', 'image2_id'),
        schema='guidebook',
    )
    op.create_index(
        op.f('ix_guidebook_dismissed_image_duplicates_image2_id'),
        'dismissed_image_duplicates',
        ['image2_id'],
        unique=False,
        schema='guidebook',
    )


def downgrade():
    op.drop_index(
        op.f('ix_guidebook_dismissed_image_duplicates_image2_id'),
        table_name='dismissed_image_duplicates',
        schema='guidebook',
    )
    op.drop_table('dismissed_image_duplicates', schema='guidebook')
