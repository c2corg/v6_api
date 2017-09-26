"""Add langs feed filter

Revision ID: 8c230a4a0284
Revises: d4d360ef69bc
Create Date: 2017-09-13 15:28:23.441323

"""
from alembic import op
import sqlalchemy as sa
from alembic_migration.extensions import drop_enum
from c2corg_api.models.utils import ArrayOfEnum

# revision identifiers, used by Alembic.
revision = '8c230a4a0284'
down_revision = 'd4d360ef69bc'
branch_labels = None
depends_on = None

def upgrade():
    langs = ('fr', 'it', 'de', 'en', 'es', 'ca', 'eu')
    lang_enum = sa.Enum(*langs, name='lang', schema='guidebook')
    lang_enum.create(op.get_bind(), checkfirst=False)

    op.add_column(
        'user',
        sa.Column(
            'feed_filter_langs',
            ArrayOfEnum(lang_enum),
            server_default='{}',
            nullable=False),
        schema='users')

    op.add_column(
        'feed_document_changes',
        sa.Column(
            'langs',
            ArrayOfEnum(lang_enum),
            server_default='{}',
            nullable=False),
        schema='guidebook')
    # fill the new col in
    op.execute("""
        with langs_for_documents as (
          select document_id, array_agg(lang)::guidebook.lang[] as langs from guidebook.documents_locales group by document_id
        )
        update guidebook.feed_document_changes as c
        set langs = dl.langs
        from langs_for_documents dl
        where c.document_id = dl.document_id""")


def downgrade():
    op.drop_column('user', 'feed_filter_langs', schema='users')
    op.drop_column('feed_document_changes', 'langs', schema='guidebook')
    drop_enum('lang', schema='guidebook')
