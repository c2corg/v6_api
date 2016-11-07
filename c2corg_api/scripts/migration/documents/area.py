from c2corg_api.models.area import Area, ArchiveArea, AREA_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY


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
            'select count(*) '
            'from app_areas_archives aa join areas a on aa.id = a.id '
            'where a.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   aa.id, aa.document_archive_id, aa.is_latest_version, '
            '   aa.is_protected, aa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(aa.geom, 3857)) geom, '
            '   aa.area_type '
            'from app_areas_archives aa join areas a on aa.id = a.id '
            'where a.redirects_to is null '
            'order by aa.id, aa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_areas_i18n_archives aa join areas a on aa.id = a.id '
            'where a.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   aa.id, aa.document_i18n_archive_id, aa.is_latest_version, '
            '   aa.culture, aa.name, aa.description '
            'from app_areas_i18n_archives aa join areas a on aa.id = a.id '
            'where a.redirects_to is null '
            'order by aa.id, aa.culture, aa.document_i18n_archive_id;'
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
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)
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
