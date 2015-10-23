from cornice.resource import resource, view
from functools32 import lru_cache

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint)
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import json_view
from c2corg_api.views.validation import (
    validate_id, check_required_fields, check_duplicate_locales)
from c2corg_common.fields_waypoint import fields_waypoint


def validate_waypoint_create(request):
    waypoint = request.validated
    validate_waypoint(waypoint, request, updating=False)


def validate_waypoint_update(request):
    waypoint = request.validated.get('document')

    if waypoint:
        validate_waypoint(waypoint, request, updating=True)


@lru_cache(maxsize=None)
def adapt_schema_for_type(waypoint_type):
    """Get the schema for a waypoint type.
    The schemas are cached.
    """
    fields = fields_waypoint.get(waypoint_type).get('fields')
    return restrict_schema(schema_waypoint, fields)


def adapt_schema(_base_schema, waypoint):
    waypoint_type = waypoint.waypoint_type
    return adapt_schema_for_type(waypoint_type)


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(Waypoint, schema_waypoint, adapt_schema)

    @view(validators=validate_id)
    def get(self):
        return self._get(Waypoint, schema_waypoint, adapt_schema)

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
    check_duplicate_locales(waypoint, request)
