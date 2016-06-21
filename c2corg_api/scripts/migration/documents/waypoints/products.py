from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.document import DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateProducts(MigrateWaypoints):

    def get_name(self):
        return 'products'

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_products_archives pa join products p on pa.id = p.id '
            'where p.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   pa.id, pa.document_archive_id, pa.is_latest_version, '
            '   pa.elevation, pa.is_protected, pa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(pa.geom, 3857)) geom, '
            '   pa.product_type, pa.url '
            'from app_products_archives pa join products p on pa.id = p.id '
            'where p.redirects_to is null '
            'order by pa.id, pa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_products_i18n_archives pa '
            '  join products p on pa.id = p.id '
            'where p.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   pa.id, pa.document_i18n_archive_id, pa.is_latest_version, '
            '   pa.culture, pa.name, pa.description, pa.hours, pa.access '
            'from app_products_i18n_archives pa '
            '  join products p on pa.id = p.id '
            'where p.redirects_to is null '
            'order by pa.id, pa.culture, pa.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type='local_product',
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            product_types=self.convert_types(
                document_in.product_type,
                MigrateProducts.product_types, [0]),
            url=document_in.url,
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=WAYPOINT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,
            access=document_in.access,
            access_period=document_in.hours
        )

    product_types = {
        '1': 'farm_sale',
        '2': 'restaurant',
        '3': 'grocery',
        '4': 'bar',
        '5': 'sport_shop'
    }
