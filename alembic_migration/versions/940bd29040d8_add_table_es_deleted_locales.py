"""Add table es_deleted_locales

Revision ID: 940bd29040d8
Revises: 8cc46db2c515
Create Date: 2017-04-06 11:53:43.889917

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '940bd29040d8'
down_revision = '8cc46db2c515'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'es_deleted_locales',
        sa.Column('document_id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(1)),
        sa.Column('lang', sa.String(2), nullable=False),
        sa.Column(
            'deleted_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False, index=True),
        sa.ForeignKeyConstraint(['lang'], ['guidebook.langs.lang'], ),
        schema='guidebook')


def downgrade():
    op.drop_table('es_deleted_locales', schema='guidebook')
