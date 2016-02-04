import transaction
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class MigrateAreaAssociations(MigrateBase):
    """Initialize associations between areas and documents.
    """

    def migrate(self):
        self.start('area associations')

        with transaction.manager:
            self.session_target.execute(SQL_CREATE_AREA_ASSOCIATIONS)
            zope.sqlalchemy.mark_changed(self.session_target)

        # run vacuum on the table (must be outside a transaction)
        engine = self.session_target.bind
        conn = engine.connect()
        old_lvl = conn.connection.isolation_level
        conn.connection.set_isolation_level(0)
        conn.execute('vacuum analyze guidebook.area_associations;')
        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()


SQL_CREATE_AREA_ASSOCIATIONS = """
insert into guidebook.area_associations (document_id, area_id) (
  select d.document_id, a.document_id as area_document_id
  from (select g.document_id, g.geom from
    guidebook.documents_geometries g join guidebook.documents d
    on g.document_id = d.document_id and d.type <> 'a') d
  join (select ga.document_id, ga.geom from
    guidebook.areas a join guidebook.documents_geometries ga
    on ga.document_id = a.document_id) a
  on ST_Intersects(d.geom, a.geom));
"""
