"""Move the coverages of Navitia out of the documents.

Revision ID: 97e65791be32
Revises: bebcc64ff5cb
Create Date: 2026-11-22 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '97e65791be32'
down_revision = 'bebcc64ff5cb'
branch_labels = None
depends_on = None

# PostgreSQL 9.6 in production: no newer SQL.

# The coverages were documents of type 'v' without history nor locale, with
# their polygon in documents_geometries.geom_detail: in longitude and latitude
# although tagged 3857, as update_navitia_coverage.sh saved them. A polygon
# really in 3857 is transformed.
COPY_SQL = """
INSERT INTO guidebook.navitia_coverages (coverage_type, geom)
SELECT DISTINCT ON (c.coverage_type) c.coverage_type,
       ST_Multi(CASE
         WHEN ST_XMin(g.geom_detail) < -180 OR ST_XMax(g.geom_detail) > 180
           OR ST_YMin(g.geom_detail) < -90 OR ST_YMax(g.geom_detail) > 90
         THEN ST_Transform(ST_SetSRID(g.geom_detail, 3857), 4326)
         ELSE ST_SetSRID(g.geom_detail, 4326)
       END)
FROM guidebook.coverages c
JOIN guidebook.documents_geometries g ON g.document_id = c.document_id
WHERE c.coverage_type IS NOT NULL
  AND GeometryType(g.geom_detail) IN ('POLYGON', 'MULTIPOLYGON')
ORDER BY c.coverage_type, c.document_id DESC
"""

# everything referring to the coverage documents, children first
DELETE_SQL = [
    'DELETE FROM guidebook.documents_topics t USING guidebook.documents_locales l '
    'WHERE t.document_locale_id = l.id AND l.document_id IN ({ids})',
    'DELETE FROM guidebook.area_associations WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.map_associations WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.associations '
    'WHERE parent_document_id IN ({ids}) OR child_document_id IN ({ids})',
    'DELETE FROM guidebook.association_log '
    'WHERE parent_document_id IN ({ids}) OR child_document_id IN ({ids})',
    'DELETE FROM guidebook.feed_document_changes WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.favourites WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.favourites_log WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.cache_versions WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_versions WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_locales_archives WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_geometries_archives WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_archives WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_locales WHERE document_id IN ({ids})',
    'DELETE FROM guidebook.documents_geometries WHERE document_id IN ({ids})',
]
COVERAGE_IDS = "SELECT document_id FROM guidebook.documents WHERE type = 'v'"


def upgrade():
    op.execute(
        """
        CREATE TABLE guidebook.navitia_coverages (
            coverage_type guidebook.coverage_type NOT NULL,
            geom geometry(MULTIPOLYGON, 4326) NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            PRIMARY KEY (coverage_type)
        )
        """
    )
    op.execute(COPY_SQL)

    for sql in DELETE_SQL:
        op.execute(sql.format(ids=COVERAGE_IDS))
    op.execute('DROP TABLE guidebook.coverages')
    # dropped from the first migration of the coverages after it ran somewhere
    op.execute('DROP TABLE IF EXISTS guidebook.coverages_archives')
    op.execute("DELETE FROM guidebook.deleted_documents WHERE document_type = 'v'")
    op.execute(f'DELETE FROM guidebook.documents WHERE document_id IN ({COVERAGE_IDS})')


def downgrade():
    op.execute(
        """
        CREATE TABLE guidebook.coverages (
            coverage_type guidebook.coverage_type,
            document_id integer NOT NULL
                REFERENCES guidebook.documents (document_id),
            PRIMARY KEY (document_id)
        )
        """
    )
    # a document by coverage again, its polygon tagged 3857 as before
    op.execute(
        """
        DO $$
        DECLARE
          c record;
          new_id integer;
        BEGIN
          FOR c IN SELECT * FROM guidebook.navitia_coverages
                   ORDER BY coverage_type LOOP
            INSERT INTO guidebook.documents (type, version, quality, protected)
            VALUES ('v', 1, 'draft', false)
            RETURNING document_id INTO new_id;
            INSERT INTO guidebook.coverages (coverage_type, document_id)
            VALUES (c.coverage_type, new_id);
            INSERT INTO guidebook.documents_geometries
              (version, document_id, geom_detail)
            VALUES (1, new_id, ST_SetSRID(c.geom, 3857));
          END LOOP;
        END
        $$
        """
    )
    op.execute('DROP TABLE guidebook.navitia_coverages')
