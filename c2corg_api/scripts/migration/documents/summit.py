from c2corg_api.models.document import DocumentGeometry, \
    ArchiveDocumentGeometry
from c2corg_api.models.waypoint import Waypoint, ArchiveWaypoint, \
    WaypointLocale, ArchiveWaypointLocale
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class MigrateSummits(MigrateDocuments):

    def get_name(self):
        return 'summits'

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
            version=version,
            waypoint_type=self.convert_type(document_in.summit_type),
            elevation=document_in.elevation,
            maps_info=document_in.maps_info
        )

    def get_document_archive(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.document_archive_id,
            version=version,
            waypoint_type=self.convert_type(document_in.summit_type),
            elevation=document_in.elevation,
            maps_info=document_in.maps_info
        )

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_document_geometry_archive(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.document_archive_id,
            version=version,
            geom=document_in.geom
        )

    def get_document_locale(self, document_in, version):
        # TODO extract summary
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            version=version,
            culture=document_in.culture,
            title=document_in.name,
            description=document_in.description
        )

    def get_document_locale_archive(self, document_in, version):
        # TODO extract summary
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            version=version,
            culture=document_in.culture,
            title=document_in.name,
            description=document_in.description
        )

    summit_types = {
        '1': 'summit',    # was 'culmen'
        '2': 'pass',
        '4': 'cliff',
        '6': 'locality',  # was 'valley'
        '3': 'lake',
        '7': 'glacier',
        '8': 'bisse',
        '9': 'source',
        '10': 'misc',     # was 'canyon' ?
        '11': 'pit',      # was': 'hole'
        '100': 'hut',
        '5': 'misc',      # was 'raid' ?
        '99': 'misc'      # was 'other'
    }

    def convert_type(self, summit_type_index):
        summit_type = str(summit_type_index)
        if summit_type in MigrateSummits.summit_types:
            return MigrateSummits.summit_types[summit_type]
        else:
            raise AssertionError(
                'invalid summit type: {0}'.format(summit_type))
