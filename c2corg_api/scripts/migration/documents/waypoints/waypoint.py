from c2corg_api.models.document import DocumentGeometry, \
    ArchiveDocumentGeometry
from c2corg_api.models.waypoint import Waypoint, ArchiveWaypoint, \
    WaypointLocale, ArchiveWaypointLocale
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


class MigrateWaypoints(MigrateDocuments):

    def get_model_document(self, locales):
        return WaypointLocale if locales else Waypoint

    def get_model_archive_document(self, locales):
        return ArchiveWaypointLocale if locales else ArchiveWaypoint

    def get_model_geometry(self):
        return DocumentGeometry

    def get_model_archive_geometry(self):
        return ArchiveDocumentGeometry

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

    def get_document_locale_archive(self, document_in, version):
        return self.get_document_locale(document_in, version)
