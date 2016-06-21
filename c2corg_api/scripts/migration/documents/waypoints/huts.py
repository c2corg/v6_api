from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.document import DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints
from c2corg_common.attributes import custodianship_types


class MigrateHuts(MigrateWaypoints):

    def get_name(self):
        return 'huts'

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_huts_archives ha join huts h on ha.id = h.id '
            'where h.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   ha.id, ha.document_archive_id, ha.is_latest_version, '
            '   ha.elevation, ha.is_protected, ha.redirects_to, '
            '   ST_Force2D(ST_SetSRID(ha.geom, 3857)) geom, '
            '   ha.shelter_type, ha.is_staffed, ha.phone, ha.url, '
            '   ha.staffed_capacity, ha.unstaffed_capacity, '
            '   ha.has_unstaffed_matress, ha.has_unstaffed_blanket, '
            '   ha.has_unstaffed_gas, ha.has_unstaffed_wood '
            'from app_huts_archives ha join huts h on ha.id = h.id '
            'where h.redirects_to is null '
            'order by ha.id, ha.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_huts_i18n_archives ha join huts h on ha.id = h.id '
            'where h.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   ha.id, ha.document_i18n_archive_id, ha.is_latest_version, '
            '   ha.culture, ha.name, ha.description, ha.pedestrian_access, '
            '   ha.staffed_period '
            'from app_huts_i18n_archives ha join huts h on ha.id = h.id '
            'where h.redirects_to is null '
            'order by ha.id, ha.culture, ha.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        waypoint_type = self.convert_type(
                document_in.shelter_type, MigrateHuts.shelter_types)
        if waypoint_type is None:
            waypoint_type = 'hut'

        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type=waypoint_type,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            custodianship=self.get_custodianship(document_in),
            phone=document_in.phone,
            url=document_in.url,
            capacity_staffed=document_in.staffed_capacity,
            capacity=document_in.unstaffed_capacity,
            matress_unstaffed=self.convert_type(
                document_in.has_unstaffed_matress, MigrateHuts.boolean_types),
            blanket_unstaffed=self.convert_type(
                document_in.has_unstaffed_blanket, MigrateHuts.boolean_types),
            gas_unstaffed=self.convert_type(
                document_in.has_unstaffed_gas, MigrateHuts.boolean_types),
            heating_unstaffed=self.convert_type(
                document_in.has_unstaffed_wood, MigrateHuts.boolean_types),
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
            access=document_in.pedestrian_access,
            access_period=document_in.staffed_period
        )

    def get_custodianship(self, document_in):
        if document_in.is_staffed is None:
            return None
        if document_in.is_staffed:
            if document_in.unstaffed_capacity == 0:
                return custodianship_types[0]  # accessible when wardened
            else:
                return custodianship_types[1]  # always accessible
        return custodianship_types[3]  # no warden

    shelter_types = {
        '1': 'hut',
        '5': 'gite',
        '2': 'shelter',
        '3': 'bivouac',
        '4': 'base_camp',
        '6': 'camp_site'
    }

    boolean_types = {
        '1': False,
        '8': True,
        '0': None,
        '10': None  # non applicable
    }
