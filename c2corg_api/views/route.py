from cornice.resource import resource, view
from functools32.functools32 import lru_cache

from c2corg_api.models.route import Route, schema_route, schema_update_route
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor
from c2corg_api.views import json_view
from c2corg_api.views.validation import validate_id
from c2corg_common.fields_route import fields_route


validate_route_create = make_validator_create(fields_route, 'route_type')
validate_route_update = make_validator_update(fields_route, 'route_type')


@lru_cache(maxsize=None)
def adapt_schema_for_type(route_type, field_list_type):
    """Get the schema for a route type.
    `field_list_type` should be either "fields" or "listing".
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_route.get(route_type).get(field_list_type)
    return restrict_schema(schema_route, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'route_type', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_type, 'route_type', 'listing')


@resource(collection_path='/routes', path='/routes/{id}')
class RouteRest(DocumentRest):

    def collection_get(self):
        return self._collection_get(
            Route, schema_route, listing_schema_adaptor)

    @view(validators=validate_id)
    def get(self):
        return self._get(Route, schema_route, schema_adaptor)

    @json_view(schema=schema_route, validators=validate_route_create)
    def collection_post(self):
        return self._collection_post(Route, schema_route)

    @json_view(schema=schema_update_route,
               validators=[validate_id, validate_route_update])
    def put(self):
        return self._put(Route, schema_route)
