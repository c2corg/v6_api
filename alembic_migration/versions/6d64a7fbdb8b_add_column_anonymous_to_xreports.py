"""Add column anonymous to xreports

Revision ID: 6d64a7fbdb8b
Revises: ff894861149d
Create Date: 2017-06-23 14:18:18.929235

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d64a7fbdb8b'
down_revision = 'ff894861149d'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'xreports',
        sa.Column('anonymous', sa.Boolean()),
        schema='guidebook')
    op.add_column(
        'xreports_archives',
        sa.Column('anonymous', sa.Boolean()),
        schema='guidebook')


def downgrade():
    op.drop_column('xreports', 'anonymous', schema='guidebook')
    op.drop_column('xreports_archives', 'anonymous', schema='guidebook')
