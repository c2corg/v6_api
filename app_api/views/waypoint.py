from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from app_api.models.waypoint import Waypoint, schema_waypoint
from app_api.models import DBSession
from . import validate_id, to_json_dict


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(object):

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        return {'waypoints': []}

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

        return to_json_dict(waypoint, schema_waypoint)
