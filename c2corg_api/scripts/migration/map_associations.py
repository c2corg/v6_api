import transaction
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class MigrateMapAssociations(MigrateBase):
    """Initialize associations between maps and documents.
    """

    def migrate(self):
        self.start('map associations')

        with transaction.manager:
            self.session_target.execute(SQL_CREATE_MAP_ASSOCIATIONS)
            zope.sqlalchemy.mark_changed(self.session_target)

        self.stop()


SQL_CREATE_MAP_ASSOCIATIONS = """
insert into guidebook.map_associations (document_id, topo_map_id) (
  select d.document_id, a.document_id as map_document_id
  from (select g.document_id, g.geom, g.geom_detail from
    guidebook.documents_geometries g join guidebook.documents d
    on g.document_id = d.document_id and d.type <> 'm') d
  join (select ga.document_id, ga.geom_detail from
    guidebook.maps a join guidebook.documents_geometries ga
    on ga.document_id = a.document_id) a
  on ST_Intersects(d.geom, a.geom_detail) or
     ST_Intersects(d.geom_detail, a.geom_detail));
"""
