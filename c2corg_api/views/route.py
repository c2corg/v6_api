from cornice.resource import resource, view

from c2corg_api.models.route import Route, schema_route, schema_update_route, \
    ArchiveRoute, ArchiveRouteLocale
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update, make_schema_adaptor, get_all_fields
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id
from c2corg_common.fields_route import fields_route
from c2corg_common.attributes import activities

validate_route_create = make_validator_create(
    fields_route, 'activities', activities)
validate_route_update = make_validator_update(
    fields_route, 'activities', activities)


def adapt_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_route, activities, field_list_type)
    return restrict_schema(schema_route, fields)


schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'fields')
listing_schema_adaptor = make_schema_adaptor(
    adapt_schema_for_activities, 'activities', 'listing')


@resource(collection_path='/routes', path='/routes/{id}',
          cors_policy=cors_policy)
class RouteRest(DocumentRest):

    @view(validators=validate_pagination)
    def collection_get(self):
        return self._collection_get(
            Route, schema_route, listing_schema_adaptor)

    @view(validators=validate_id)
    def get(self):
        return self._get(Route, schema_route, schema_adaptor)

    @restricted_json_view(schema=schema_route,
                          validators=validate_route_create)
    def collection_post(self):
        return self._collection_post(Route, schema_route)

    @restricted_json_view(schema=schema_update_route,
                          validators=[validate_id, validate_route_update])
    def put(self):
        return self._put(Route, schema_route)


@resource(path='/routes/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class RouteVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveRoute, ArchiveRouteLocale, schema_route, schema_adaptor)
