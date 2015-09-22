from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from app_api.models.waypoint import Waypoint, schema_waypoint
from app_api.models import DBSession
from app_api.ext import caching
from app_api.views.document import DocumentRest
from . import validate_id, to_json_dict


cache_region = caching.get_region()


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        waypoints = DBSession. \
            query(Waypoint). \
            options(joinedload(Waypoint.locales)). \
            limit(30)

        return [to_json_dict(wp, schema_waypoint) for wp in waypoints]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']
        return self._get_by_id(id)

    @cache_region.cache_on_arguments()
    def _get_by_id(self, id):
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
