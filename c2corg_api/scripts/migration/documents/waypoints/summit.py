from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.document import DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateSummits(MigrateWaypoints):

    def get_name(self):
        return 'summits'

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_summits_archives sa join summits s on sa.id = s.id '
            'where s.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select sa.id, sa.document_archive_id, sa.is_latest_version, '
            'sa.elevation, sa.summit_type, sa.maps_info, sa.is_protected, '
            'sa.redirects_to, ST_Force2D(ST_SetSRID(sa.geom, 3857)) geom '
            'from app_summits_archives sa join summits s on sa.id = s.id '
            'where s.redirects_to is null '
            'order by sa.id, sa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_summits_i18n_archives sa join summits s on sa.id = s.id '
            'where s.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select sa.id, sa.document_i18n_archive_id, sa.is_latest_version, '
            'sa.culture, sa.name, sa.description '
            'from app_summits_i18n_archives sa join summits s on sa.id = s.id '
            'where s.redirects_to is null '
            'order by sa.id, sa.document_i18n_archive_id;'
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
            maps_info=document_in.maps_info,
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
            summary=summary
        )

    summit_types = {
        '1':   'summit',            # was 'culmen'
        '2':   'pass',
        '4':   'climbing_outdoor',  # was 'cliff'
        '6':   'locality',          # was 'valley'
        '3':   'lake',
        '7':   'misc',              # was 'glacier'
        '8':   'bisse',
        '9':   'waterpoint',        # was 'source'
        '10':  'canyon',
        '11':  'cave',              # was': 'hole'
        '100': 'hut',
        '5':   'virtual',           # was 'raid'
        '99':  'misc'               # was 'other'
    }
