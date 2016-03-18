from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.models.topo_map import TopoMap, ArchiveTopoMap, MAP_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class MigrateMaps(MigrateDocuments):

    def get_name(self):
        return 'maps'

    def get_model_document(self, locales):
        return DocumentLocale if locales else TopoMap

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveTopoMap

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom_detail=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_maps_archives ma join maps m on ma.id = m.id '
            'where m.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   ma.id, ma.document_archive_id, ma.is_latest_version, '
            '   ma.is_protected, ma.redirects_to, '
            '   ST_Force2D(ST_SetSRID(ma.geom, 3857)) geom, '
            '   ma.editor, ma.scale, ma.code '
            'from app_maps_archives ma join maps m on ma.id = m.id '
            'where m.redirects_to is null '
            'order by ma.id, ma.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_maps_i18n_archives ma join maps m on ma.id = m.id '
            'where m.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   ma.id, ma.document_i18n_archive_id, ma.is_latest_version, '
            '   ma.culture, ma.name, ma.description '
            'from app_maps_i18n_archives ma join maps m on ma.id = m.id '
            'where m.redirects_to is null  '
            'order by ma.id, ma.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=MAP_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            code=document_in.code,
            editor=self.convert_type(document_in.editor, MigrateMaps.editors),
            scale=self.convert_type(document_in.scale, MigrateMaps.scales),
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=DOCUMENT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary
        )

    scales = {
        '1': '25000',
        '2': '50000',
        '3': '100000',
    }

    editors = {
        '1': 'IGN',
        '2': 'Swisstopo',
        '3': 'Escursionista',
    }
