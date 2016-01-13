from c2corg_api.models import DBSession
from c2corg_api.models.document import UpdateType
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.search.sync import sync_search_index
from c2corg_api.views.route import set_route_title_prefix
from cornice.resource import resource, view

from c2corg_api.models.waypoint import (
    Waypoint, schema_waypoint, schema_update_waypoint,
    ArchiveWaypoint, ArchiveWaypointLocale)

from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update,
    make_schema_adaptor)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_common.fields_waypoint import fields_waypoint
from c2corg_common.attributes import waypoint_types
from functools import lru_cache
from sqlalchemy.orm import joinedload, load_only

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

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            Waypoint, schema_waypoint, listing_schema_adaptor)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Waypoint, schema_waypoint, schema_adaptor)

    @restricted_json_view(schema=schema_waypoint,
                          validators=validate_waypoint_create)
    def collection_post(self):
        return self._collection_post(Waypoint, schema_waypoint)

    @restricted_json_view(schema=schema_update_waypoint,
                          validators=[validate_id, validate_waypoint_update])
    def put(self):
        return self._put(
            Waypoint, schema_waypoint, after_update=update_linked_route_titles)


@resource(path='/waypoints/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class WaypointVersionRest(DocumentRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveWaypoint, ArchiveWaypointLocale, schema_waypoint,
            schema_adaptor)


def update_linked_route_titles(waypoint, update_types):
    """When a waypoint is the main waypoint of a route, the field
    `title_prefix`, which caches the waypoint name, has to be updated.
    This method takes care of updating all routes, that the waypoint is
    "main waypoint" of.
    """
    if UpdateType.LANG not in update_types:
        # if the locales did not change, no need to continue
        return

    linked_routes = DBSession.query(Route). \
        filter(Route.main_waypoint_id == waypoint.document_id). \
        options(joinedload(Route.locales).load_only(
            RouteLocale.culture, RouteLocale.id)). \
        options(load_only(Route.document_id)). \
        all()

    if linked_routes:
        waypoint_locales = waypoint.locales
        waypoint_locales_index = {
            locale.culture: locale for locale in waypoint_locales}

        for route in linked_routes:
            set_route_title_prefix(
                route, waypoint_locales, waypoint_locales_index)
            sync_search_index(route)
