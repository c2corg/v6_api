from c2corg_api.models.waypoint import (
    ArchiveWaypoint,
    ArchiveWaypointLocale,
    Waypoint,
    WaypointLocale,
)
from c2corg_api.scripts.migration_v5.documents.document import MigrateDocuments


class MigrateWaypoints(MigrateDocuments):
    def get_model_document(self, locales):
        return WaypointLocale if locales else Waypoint

    def get_model_archive_document(self, locales):
        return ArchiveWaypointLocale if locales else ArchiveWaypoint

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom,
        )
