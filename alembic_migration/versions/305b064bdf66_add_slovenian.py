"""Add Slovenian

Revision ID: 305b064bdf66
Revises: 1bfd4ff6d3f8
Create Date: 2023-01-05 08:37:27.711800

"""
from c2corg_api.models.common.attributes import default_langs
from alembic_migration.extensions import drop_enum
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '305b064bdf66'
down_revision = '1bfd4ff6d3f8'
branch_labels = None
depends_on = None

# See 2c90b2e5ca7e_add_chinese.py for detailed explanations

def upgrade():
    conn = op.get_bind()
    res = conn.execute("SELECT count(1) FROM guidebook.langs").fetchall()

    if res[0][0] != 0:
        op.execute("INSERT INTO guidebook.langs VALUES ('sl');")

    # rename the existing enum type
    op.execute("ALTER TYPE guidebook.lang RENAME TO lang_old;")

    # create the new type
    lang_enum = sa.Enum(*default_langs, name='lang', schema='guidebook')
    lang_enum.create(op.get_bind(), checkfirst=False)

    # update the columns to use the new type
    op.execute("""ALTER TABLE users.user
                    ALTER COLUMN feed_filter_langs DROP DEFAULT,
                    ALTER COLUMN feed_filter_langs TYPE guidebook.lang[] USING feed_filter_langs::text::guidebook.lang[],
                    ALTER COLUMN feed_filter_langs SET DEFAULT '{}'::guidebook.lang[];""")

    op.execute("""ALTER TABLE guidebook.feed_document_changes
                    ALTER COLUMN langs DROP DEFAULT,
                    ALTER COLUMN langs TYPE guidebook.lang[] USING langs::text::guidebook.lang[],
                    ALTER COLUMN langs SET DEFAULT '{}'::guidebook.lang[];""")

    # remove the old type
    drop_enum("lang_old", "guidebook")


def downgrade():
    op.execute("DELETE FROM guidebook.langs WHERE lang='sl';")