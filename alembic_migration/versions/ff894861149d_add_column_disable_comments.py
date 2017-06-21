"""Add column disable_comments

Revision ID: ff894861149d
Revises: bacd59c5806a
Create Date: 2017-06-21 14:34:08.421642

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff894861149d'
down_revision = 'bacd59c5806a'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'outings',
        sa.Column('disable_comments', sa.Boolean()),
        schema='guidebook')
    op.add_column(
        'outings_archives',
        sa.Column('disable_comments', sa.Boolean()),
        schema='guidebook')
    op.add_column(
        'xreports',
        sa.Column('disable_comments', sa.Boolean()),
        schema='guidebook')
    op.add_column(
        'xreports_archives',
        sa.Column('disable_comments', sa.Boolean()),
        schema='guidebook')


def downgrade():
    op.drop_column('outings', 'disable_comments', schema='guidebook')
    op.drop_column('outings_archives', 'disable_comments', schema='guidebook')
    op.drop_column('xreports', 'disable_comments', schema='guidebook')
    op.drop_column('xreports_archives', 'disable_comments', schema='guidebook')
