from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateSummits(MigrateWaypoints):

    def get_name(self):
        return 'summits'

    def get_count_query(self):
        return (
            'select count(*) from app_summits_archives'
        )

    def get_query(self):
        return (
            'select id, document_archive_id, is_latest_version, elevation, '
            'summit_type, maps_info, is_protected, redirects_to, '
            'ST_Force2D(ST_SetSRID(geom, 3857)) geom '
            'from app_summits_archives '
            'order by id, document_archive_id'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_summits_i18n_archives'
        )

    def get_query_locales(self):
        return (
            'select id, document_i18n_archive_id, is_latest_version, culture, '
            'name, description '
            'from app_summits_i18n_archives '
            'order by id, document_i18n_archive_id'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type=self.convert_type(
                document_in.summit_type, MigrateSummits.summit_types),
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            maps_info=document_in.maps_info
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
            summary=summary
        )

    summit_types = {
        '1': 'summit',    # was 'culmen'
        '2': 'pass',
        '4': 'cliff',
        '6': 'locality',  # was 'valley'
        '3': 'lake',
        '7': 'glacier',
        '8': 'bisse',
        '9': 'waterpoint',
        '10': 'misc',     # was 'canyon' ?
        '11': 'pit',      # was': 'hole'
        '100': 'hut',
        '5': 'virtual',   # was 'raid'
        '99': 'misc'      # was 'other'
    }
