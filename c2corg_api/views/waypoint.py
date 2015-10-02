from cornice.resource import resource, view

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint)
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import validate_id


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(Waypoint, schema_waypoint)

    @view(validators=validate_id)
    def get(self):
        return self._get(Waypoint, schema_waypoint)

    @view(schema=schema_waypoint)
    def collection_post(self):
        return self._collection_post(Waypoint, schema_waypoint)

    @view(schema=schema_update_waypoint, validators=validate_id)
    def put(self):
        return self._put(Waypoint, schema_waypoint)
