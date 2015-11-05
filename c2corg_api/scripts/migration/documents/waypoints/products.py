from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateProducts(MigrateWaypoints):

    def get_name(self):
        return 'products'

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
            type='w',
            version=version,
            waypoint_type='local_product',
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            product_types=self.convert_types(
                document_in.product_type,
                MigrateProducts.product_types, [0]),
            url=document_in.url
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type='w',
            version=version,
            culture=document_in.culture,
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
