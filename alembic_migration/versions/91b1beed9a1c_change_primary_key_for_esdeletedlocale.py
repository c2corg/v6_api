"""Change primary key for ESDeletedLocale

Revision ID: 91b1beed9a1c
Revises: 940bd29040d8
Create Date: 2017-04-12 10:24:25.216239

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '91b1beed9a1c'
down_revision = '8e0f02982746'
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint(
        'es_deleted_locales_pkey', 'es_deleted_locales',
        type_='primary', schema='guidebook')
    op.create_primary_key(
        'es_deleted_locales_pkey', 'es_deleted_locales',
        ['document_id', 'lang'], schema='guidebook')


def downgrade():
    op.drop_constraint(
        'es_deleted_locales_pkey', 'es_deleted_locales',
        type_='primary', schema='guidebook')
    op.create_primary_key(
        'es_deleted_locales_pkey', 'es_deleted_locales',
        ['document_id'], schema='guidebook')
