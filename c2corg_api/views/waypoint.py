from cornice.resource import resource, view

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint)
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import json_view
from c2corg_api.views.validation import validate_id, check_required_fields
from c2corg_api.fields_waypoint import fields_waypoint


def validate_waypoint_create(request):
    waypoint = request.validated
    validate_waypoint(waypoint, request, updating=False)


def validate_waypoint_update(request):
    waypoint = request.validated.get('document')

    if waypoint:
        validate_waypoint(waypoint, request, updating=True)


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(Waypoint, schema_waypoint)

    @view(validators=validate_id)
    def get(self):
        return self._get(Waypoint, schema_waypoint)

    @json_view(schema=schema_waypoint, validators=validate_waypoint_create)
    def collection_post(self):
        return self._collection_post(Waypoint, schema_waypoint)

    @json_view(schema=schema_update_waypoint,
               validators=[validate_id, validate_waypoint_update])
    def put(self):
        return self._put(Waypoint, schema_waypoint)


def validate_waypoint(waypoint, request, updating):
    """Checks that all required fields are given.
    """
    waypoint_type = waypoint.get('waypoint_type')

    if not waypoint_type:
        # can't do the validation without the type (an error was already added
        # when validating the Colander schema)
        return

    fields = fields_waypoint.get(waypoint_type)
    check_required_fields(waypoint, fields['required'], request, updating)
