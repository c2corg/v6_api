from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from app_api.models.waypoint import Waypoint, schema_waypoint
from app_api.models.document_history import HistoryMetaData, DocumentVersion
from app_api.models import DBSession
from . import validate_id, to_json_dict


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(object):

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        waypoints = DBSession. \
            query(Waypoint). \
            options(joinedload(Waypoint.locales)). \
            all()

        return [to_json_dict(wp, schema_waypoint) for wp in waypoints]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']

        waypoint = DBSession. \
            query(Waypoint). \
            filter(Waypoint.document_id == id). \
            options(joinedload(Waypoint.locales)). \
            first()

        return to_json_dict(waypoint, schema_waypoint)

    @view(schema=schema_waypoint)
    def collection_post(self):
        waypoint = schema_waypoint.objectify(self.request.validated)

        DBSession.add(waypoint)
        DBSession.flush()

        self._create_new_version(waypoint)

        return to_json_dict(waypoint, schema_waypoint)

    def _create_new_version(self, waypoint):
        """
        TODO This should be a generic function for all document types. Move
        into a more generic namespace and make `to_archive` and
        `get_archive_locales` abstract methods of `Document`.
        """
        archive_waypoint = waypoint.to_archive()
        archive_locales = waypoint.get_archive_locales()

        meta_data = HistoryMetaData(is_minor=False, comment='creation')
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=waypoint.document_id,
                culture=locale.culture,
                version=1,
                nature='ft',
                document_archive=archive_waypoint,
                document_i18n_archive=locale,
                history_metadata=meta_data
            )
            versions.append(version)

        DBSession.add(archive_waypoint)
        DBSession.add_all(archive_locales)
        DBSession.add(meta_data)
        DBSession.add_all(versions)
        DBSession.flush()
