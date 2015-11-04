from c2corg_api.models.document import DocumentGeometry, \
    ArchiveDocumentGeometry
from c2corg_api.models.waypoint import Waypoint, ArchiveWaypoint, \
    WaypointLocale, ArchiveWaypointLocale
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class MigrateProducts(MigrateDocuments):

    def get_name(self):
        return 'products'

    def get_model_document(self, locales):
        return WaypointLocale if locales else Waypoint

    def get_model_archive_document(self, locales):
        return ArchiveWaypointLocale if locales else ArchiveWaypoint

    def get_model_geometry(self):
        return DocumentGeometry

    def get_model_archive_geometry(self):
        return ArchiveDocumentGeometry

    def get_count_query(self):
        return (
            'select count(*) from app_products_archives;'
        )

    def get_query(self):
        return (
            'select '
            '   id, document_archive_id, is_latest_version, elevation, '
            '   is_protected, redirects_to, '
            '   ST_Force2D(ST_SetSRID(geom, 3857)) geom, '
            '   product_type, url '
            'from app_products_archives '
            'order by id, document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_products_i18n_archives;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   id, document_i18n_archive_id, is_latest_version, culture, '
            '    name, description, hours, access '
            'from app_products_i18n_archives '
            'order by id, document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            version=version,
            waypoint_type='local_product',
            elevation=document_in.elevation,
            product_types=self.convert_types(
                document_in.product_type,
                MigrateProducts.product_types, [0]),
            url=document_in.url
        )

    def get_document_archive(self, document_in, version):
        doc = self.get_document(document_in, version)
        doc['id'] = document_in.document_archive_id
        return doc

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_document_geometry_archive(self, document_in, version):
        doc = self.get_document_geometry(document_in, version)
        doc['id'] = document_in.document_archive_id
        return doc

    def get_document_locale(self, document_in, version):
        # TODO extract summary
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            version=version,
            culture=document_in.culture,
            title=document_in.name,
            description=document_in.description,
            access=document_in.access,
            access_period=document_in.hours
        )

    def get_document_locale_archive(self, document_in, version):
        return self.get_document_locale(document_in, version)

    product_types = {
        '1': 'farm_sale',
        '2': 'restaurant',
        '3': 'grocery',
        '4': 'bar',
        '5': 'sport_shop'
    }
