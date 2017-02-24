"""Add 2 columns to feed and user schema (feed language filtration)

Revision ID: ab88debfc524
Revises: 8cc46db2c515
Create Date: 2017-02-28 15:05:58.046935

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

from c2corg_api.models import utils
from alembic_migration.extensions import drop_enum
from sqlalchemy.sql.sqltypes import Enum

revision = 'ab88debfc524'
down_revision = '8cc46db2c515'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column(
            'feed_filter_lang_preferences', utils.ArrayOfEnum(Enum('fr', 'it', 'de', 'en', 'es', 'ca', 'eu', name='langs', schema='guidebook')),
            server_default='{}', nullable=False),
        schema='users')
    op.add_column(
        'feed_document_changes',
        sa.Column(
            'languages', utils.ArrayOfEnum(Enum('fr', 'it', 'de', 'en', 'es', 'ca', 'eu', name='langs', schema='guidebook')),
            server_default='{}', nullable=False),
        schema='guidebook')


def downgrade():
    op.drop_column('user', 'feed_filter_lang_preferences', schema='users')
    op.drop_column('feed_document_changes', 'languages', schema='guidebook')
