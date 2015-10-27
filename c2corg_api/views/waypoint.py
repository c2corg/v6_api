from cornice.resource import resource, view
from functools32 import lru_cache

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint)
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import json_view
from c2corg_api.views.validation import validate_id
from c2corg_common.fields_waypoint import fields_waypoint


validate_waypoint_create = make_validator_create(
    fields_waypoint, 'waypoint_type')
validate_waypoint_update = make_validator_update(
    fields_waypoint, 'waypoint_type')


@lru_cache(maxsize=None)
def adapt_schema_for_type(waypoint_type):
    """Get the schema for a waypoint type.
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_waypoint.get(waypoint_type).get('fields')
    return restrict_schema(schema_waypoint, fields)


@lru_cache(maxsize=None)
def adapt_listing_schema_for_type(waypoint_type):
    """Get the listing schema for a waypoint type.
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_waypoint.get(waypoint_type).get('listing')
    return restrict_schema(schema_waypoint, fields)


def adapt_schema(_base_schema, waypoint):
    return adapt_schema_for_type(waypoint.waypoint_type)


def adapt_listing_schema(_base_schema, waypoint):
    return adapt_listing_schema_for_type(waypoint.waypoint_type)


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(
            Waypoint, schema_waypoint, adapt_listing_schema)

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
