from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateParkings(MigrateWaypoints):

    def get_name(self):
        return 'parking'

    def get_count_query(self):
        return (
            'select count(*) from app_parkings_archives;'
        )

    def get_query(self):
        return (
            'select '
            '   id, document_archive_id, is_latest_version, elevation, '
            '   is_protected, redirects_to, '
            '   ST_Force2D(ST_SetSRID(geom, 3857)) geom,'
            '   public_transportation_rating, snow_clearance_rating, '
            '   lowest_elevation, public_transportation_types '
            'from app_parkings_archives '
            'order by id, document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_parkings_i18n_archives;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   id, document_i18n_archive_id, is_latest_version, culture, '
            '    name, description, public_transportation_description, '
            '    snow_clearance_comment, accommodation '
            'from app_parkings_i18n_archives '
            'order by id, document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type='access',
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            elevation_min=document_in.lowest_elevation,
            public_transportation_rating=self.convert_type(
                document_in.public_transportation_rating,
                MigrateParkings.public_transportation_ratings),
            snow_clearance_rating=self.convert_type(
                document_in.snow_clearance_rating,
                MigrateParkings.snow_clearance_ratings),
            public_transportation_types=self.convert_types(
                document_in.public_transportation_types,
                MigrateParkings.public_transportation_types, [0])

        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=WAYPOINT_TYPE,
            version=version,
            culture=document_in.culture,
            title=document_in.name,
            description=self.merge_text(
                description, document_in.accommodation),
            summary=summary,
            access=document_in.public_transportation_description,
            access_period=document_in.snow_clearance_comment
        )

    public_transportation_ratings = {
        '1': 'good',
        '2': 'poor',
        '3': 'no',
        '4': 'near',
        '5': 'seasonal'
    }

    snow_clearance_ratings = {
        '1': 'often',
        '2': 'sometimes',
        '3': 'naturally',
        '4': 'non_applicable'
    }

    public_transportation_types = {
        '1': 'train',
        '2': 'bus',
        '3': 'service_on_demand',
        '4': 'boat',
        '9': 'cable_car'
    }
