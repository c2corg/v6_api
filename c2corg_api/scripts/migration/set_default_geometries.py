import transaction
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class SetDefaultGeometries(MigrateBase):
    """For outings and routes set a default geometry either from an existing
    track, the associated route (for outings) or associated waypoints.
    """

    def migrate(self):
        self.start('default geometries')

        with transaction.manager:
            self.session_target.execute(SQL_ROUTE_OUTING_LINESTRING)
            self.session_target.execute(SQL_ROUTE_OUTING_MULTILINESTRING)
            self.session_target.execute(SQL_ROUTE_NO_GEOM)
            self.session_target.execute(SQL_OUTING_NO_GEOM)
            self.session_target.execute(SQL_OUTING_NO_ROUTE)
            self.session_target.execute(SQL_ROUTE_OUTING_UPDATE_ARCHIVES)
            zope.sqlalchemy.mark_changed(self.session_target)

        # run vacuum on the table (must be outside a transaction)
        engine = self.session_target.bind
        conn = engine.connect()
        old_lvl = conn.connection.isolation_level
        conn.connection.set_isolation_level(0)
        conn.execute('vacuum analyze guidebook.documents_geometries;')
        conn.execute('vacuum analyze guidebook.documents_geometries_archives;')
        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()


# for routes and outings that have a linestring as `geom_detail`, set `geom`
# to the point in the middle of the line
SQL_ROUTE_OUTING_LINESTRING = """
UPDATE guidebook.documents_geometries AS g
SET geom = ST_Force2D(ST_Line_Interpolate_Point(g.geom_detail, 0.5))
FROM guidebook.documents as d
WHERE
  g.document_id = d.document_id and
  (d.type = 'r' or d.type = 'o') and
  g.geom_detail is not null and
  ST_GeometryType(g.geom_detail) = 'ST_LineString';
"""


# for routes and outings that have a multi-linestring as `geom_detail`, set
# `geom` to the point in the middle of the first line
SQL_ROUTE_OUTING_MULTILINESTRING = """
UPDATE guidebook.documents_geometries AS g
SET geom = ST_Force2D(
  ST_Line_Interpolate_Point(ST_GeometryN(g.geom_detail, 1), 0.5))
FROM guidebook.documents as d
WHERE
  g.document_id = d.document_id and
  d.type in ('r', 'o') and
  g.geom_detail is not null and
  ST_GeometryType(g.geom_detail) = 'ST_MultiLineString';
"""


# for routes that have no `geom_detail`, set `geom` to the centroid of the
# convex hull of all associated waypoints
SQL_ROUTE_NO_GEOM = """
with v as (
  select
    rg.document_id as g_document_id,
    ST_Centroid(ST_ConvexHull(ST_Collect(wpg.geom))) centroid
  from guidebook.documents_geometries rg
    join guidebook.documents r
      on rg.document_id = r.document_id and r.type = 'r'
    join guidebook.associations a
      on r.document_id = a.child_document_id
    join guidebook.documents wp
      on a.parent_document_id = wp.document_id and wp.type = 'w'
    join guidebook.documents_geometries wpg
      on wp.document_id = wpg.document_id
  where rg.geom_detail is null
  group by rg.document_id
)
update guidebook.documents_geometries g
set geom = v.centroid
from v
where v.g_document_id = g.document_id;
"""


# for outings that have no `geom_detail`, set `geom` to the centroid of the
# convex hull of all associated routes
SQL_OUTING_NO_GEOM = """
with v as (
  select
    og.document_id as g_document_id,
    ST_Centroid(ST_ConvexHull(ST_Collect(rg.geom))) centroid
  from guidebook.documents_geometries og
    join guidebook.documents o
      on og.document_id = o.document_id and o.type = 'o'
    join guidebook.associations a
      on o.document_id = a.child_document_id
    join guidebook.documents r
      on a.parent_document_id = r.document_id and r.type = 'r'
    join guidebook.documents_geometries rg
      on r.document_id = rg.document_id
  where og.geom_detail is null
  group by og.document_id
)
update guidebook.documents_geometries g
set geom = v.centroid
from v
where v.g_document_id = g.document_id;
"""


# for outings that shave no `geom_detail` and no associated route, set `geom`
# to the centroid of the convex hull of all associated waypoint
SQL_OUTING_NO_ROUTE = """
with v as (
  select
    og.document_id as g_document_id,
    ST_Centroid(ST_ConvexHull(ST_Collect(wpg.geom))) centroid
  from guidebook.documents_geometries og
    join guidebook.documents o
      on og.document_id = o.document_id and o.type = 'o'
    join guidebook.associations a
      on o.document_id = a.child_document_id
    join guidebook.documents wp
      on a.parent_document_id = wp.document_id and wp.type = 'w'
    join guidebook.documents_geometries wpg
      on wp.document_id = wpg.document_id
  where og.geom is null
  group by og.document_id
)
update guidebook.documents_geometries g
set geom = v.centroid
from v
where v.g_document_id = g.document_id;
"""


# for outings and routes that now have a default point for `geom`, set this
# point on all archive versions
SQL_ROUTE_OUTING_UPDATE_ARCHIVES = """
with v as (
  select ga.id, g.geom
  from guidebook.documents_geometries_archives ga
    join guidebook.documents d
      on ga.document_id = d.document_id and d.type in ('r', 'o')
    join guidebook.documents_geometries g
      on d.document_id = g.document_id
  where g.geom is not null
)
update guidebook.documents_geometries_archives a
set geom = v.geom
from v
where v.id = a.id;
"""
