from c2corg_api.models.area import Area, ArchiveArea, AREA_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class MigrateAreas(MigrateDocuments):

    def get_name(self):
        return 'areas'

    def get_model_document(self, locales):
        return DocumentLocale if locales else Area

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveArea

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom_detail=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) from app_areas_archives;'
        )

    def get_query(self):
        return (
            'select '
            '   id, document_archive_id, is_latest_version, '
            '   is_protected, redirects_to, '
            '   ST_Force2D(ST_SetSRID(geom, 3857)) geom, '
            '   area_type '
            'from app_areas_archives '
            'order by id, document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_areas_i18n_archives;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   id, document_i18n_archive_id, is_latest_version, culture, '
            '   name, description '
            'from app_areas_i18n_archives '
            'order by id, document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=AREA_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            area_type=self.convert_type(
                document_in.area_type, MigrateAreas.area_types),
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

    area_types = {
        '1': 'range',
        '2': 'country',
        '3': 'admin_limits',
    }
