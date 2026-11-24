"""Simplify the tracks of outings and routes less.

Revision ID: 39ccf15da971
Revises: e7b1d94a2f60
Create Date: 2026-11-20 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '39ccf15da971'
down_revision = 'e7b1d94a2f60'
branch_labels = None
depends_on = None

# The tolerance of ST_Simplify is in EPSG:3857 units: about 0.7 m on the
# ground at 45° of latitude. 5 (about 3.5 m) made the bends of the tracks
# angular on the map of an outing. A 1 point per second track of 9.5 h keeps
# 1125 points at 2 (17 KB gzipped), 858 at 3, 588 at 5. Only the geometries
# saved from now on are concerned.
FUNCTION = """
CREATE OR REPLACE FUNCTION guidebook.simplify_geom_detail()
RETURNS TRIGGER AS
$BODY$
DECLARE
  document_type varchar;
BEGIN
  IF new.geom_detail is not null THEN
    SELECT type from guidebook.documents where document_id = new.document_id
        INTO STRICT document_type;
    {body}
  END IF;
  RETURN new;
END;
$BODY$
language plpgsql;
"""

UPGRADE_BODY = """IF document_type = 'o' THEN
      new.geom_detail := ST_Simplify(new.geom_detail, 2);
    ELSIF document_type = 'r' THEN
      new.geom_detail := ST_Simplify(new.geom_detail, 3);
    END IF;"""

DOWNGRADE_BODY = """IF document_type in ('r', 'o') THEN
      new.geom_detail := ST_Simplify(new.geom_detail, 5);
    END IF;"""


def upgrade():
    # the triggers on documents_geometries and its archives call the function
    # by name: replacing it in place keeps them
    op.execute(FUNCTION.format(body=UPGRADE_BODY))


def downgrade():
    op.execute(FUNCTION.format(body=DOWNGRADE_BODY))
