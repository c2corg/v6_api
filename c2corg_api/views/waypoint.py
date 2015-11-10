from cornice.resource import resource, view
from functools32 import lru_cache

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint)

from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update,
    make_schema_adaptor)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination
from c2corg_common.fields_waypoint import fields_waypoint
from c2corg_common.attributes import waypoint_types


validate_waypoint_create = make_validator_create(
    fields_waypoint, 'waypoint_type', waypoint_types)
validate_waypoint_update = make_validator_update(
    fields_waypoint, 'waypoint_type', waypoint_types)


@lru_cache(maxsize=None)
def adapt_schema_for_type(waypoint_type, field_list_type):
    """Get the schema for a waypoint type.
    `field_list_type` should be either "fields" or "listing".
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_waypoint.get(waypoint_type).get(field_list_type)
    return restrict_schema(schema_waypoint, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'waypoint_type', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'waypoint_type', 'listing')


@resource(collection_path='/waypoints', path='/waypoints/{id}',
          cors_policy=cors_policy)
class WaypointRest(DocumentRest):

    @view(validators=validate_pagination)
    def collection_get(self):
        return self._collection_get(
            Waypoint, schema_waypoint, listing_schema_adaptor)

    @view(validators=validate_id)
    def get(self):
        return self._get(Waypoint, schema_waypoint, schema_adaptor)

    @restricted_json_view(schema=schema_waypoint,
                          validators=validate_waypoint_create,
                          permission="authenticated")
    def collection_post(self):
        # self.request.authenticated_userid
        return self._collection_post(Waypoint, schema_waypoint)

    @restricted_json_view(schema=schema_update_waypoint,
                          validators=[validate_id, validate_waypoint_update])
    def put(self):
        return self._put(Waypoint, schema_waypoint)
