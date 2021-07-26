"""Add chinese

Revision ID: 2c90b2e5ca7e
Revises: bece9007ab83
Create Date: 2021-06-23 19:36:29.664725

"""
from c2corg_api.models.common.attributes import default_langs
from alembic_migration.extensions import drop_enum
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c90b2e5ca7e'
down_revision = 'bece9007ab83'
branch_labels = None
depends_on = None

# Two table to update
#
# 1. guidebook.langs (it's a regular table)
# 2. guidebook.lang (it's am enum)


# Useful commands:
#
# ./scripts/test.sh c2corg_api/tests//views/test_langs.py
# docker-compose exec --user postgres postgresql psql -tA -d c2corg -P pager=off -c "SELECT * FROM guidebook.langs"
# docker-compose exec --user postgres postgresql psql -tA -d c2corg -P pager=off -c "SELECT enum_range(NULL::guidebook.lang)"


# To upgrade prod, after the release, execute :
#
#      docker-compose exec api .build/venv/bin/alembic upgrade head

def upgrade():
    # We have two different situation here :
    #
    # * the production or demo database, the table has been initialized with the values at the
    #   begnining of the v6 => Russian is missing, we need to add it
    # * The test DB. The workflow here is:
    #    1. create DB
    #    2. run all migrations (this file)
    #    3. fill some table with values from python enums (the very last known one)
    #
    # The issue is that step 3 will fail, as 'zh' is still present. To tackle this, we simply check
    # if there is some value in the table. If yes, it's not a test DB and we have to complete them.

    conn = op.get_bind()
    res = conn.execute("SELECT count(1) FROM guidebook.langs").fetchall()

    if res[0][0] != 0:
        op.execute("INSERT INTO guidebook.langs VALUES ('zh');")

    # And now, the enum. As it is build and filled during the migration script (step 2), we have to add the value

    # And horror horror horror: add a new value in an PG enum ...
    # https://blog.yo1.dog/updating-enum-values-in-postgresql-the-safe-and-easy-way/

    # rename the existing type
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
    op.execute("DELETE FROM guidebook.langs WHERE lang='zh';")
