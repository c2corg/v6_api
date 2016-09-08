from c2corg_api.models.area import AREA_TYPE, Area, schema_listing_area
from c2corg_api.models.image import IMAGE_TYPE, Image, schema_listing_image
from c2corg_api.models.outing import OUTING_TYPE, Outing, schema_outing
from c2corg_api.models.route import schema_route, ROUTE_TYPE, Route, \
    RouteLocale
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap, \
    schema_listing_topo_map
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile, \
    schema_listing_user_profile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, schema_waypoint, Waypoint
from c2corg_api.views import set_author
from c2corg_common.fields_outing import fields_outing
from c2corg_common.fields_route import fields_route
from c2corg_common.fields_waypoint import fields_waypoint
from functools import lru_cache


class GetDocumentsConfig:

    def __init__(
            self, document_type, clazz, schema, clazz_locale=None,
            adapt_schema=None, include_areas=True, set_custom_fields=None):
        self.document_type = document_type
        self.clazz = clazz
        self.schema = schema
        self.clazz_locale = clazz_locale
        self.adapt_schema = adapt_schema
        self.include_areas = include_areas
        self.set_custom_fields = set_custom_fields


def make_schema_adaptor(adapt_schema_for_type, type_field, field_list_type):
    """Returns a function which adapts a base schema to a specific document
    type, e.g. it returns a function which turns the base schema for waypoints
    into a schema which contains only the fields for the waypoint type
    "summit".
    """
    def adapt_schema(_base_schema, document):
        return adapt_schema_for_type(
            getattr(document, type_field), field_list_type)
    return adapt_schema


def get_all_fields(fields, activities, field_list_type):
    """Returns all fields needed for the given list of activities.
    """
    fields_list = [
        fields.get(activity).get(field_list_type) for activity in activities
    ]
    # turn a list of lists [['a', 'b'], ['b', 'c'], ['d']] into a flat set
    # ['a', 'b', 'c', 'd']
    return set(sum(fields_list, []))


# areas


area_documents_config = GetDocumentsConfig(
    AREA_TYPE, Area, schema_listing_area, include_areas=False)


# images


image_documents_config = GetDocumentsConfig(
    IMAGE_TYPE, Image, schema_listing_image)


# outings


def adapt_outing_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_outing, activities, field_list_type)
    return restrict_schema(schema_outing, fields)

outing_schema_adaptor = make_schema_adaptor(
    adapt_outing_schema_for_activities, 'activities', 'fields')
outing_listing_schema_adaptor = make_schema_adaptor(
    adapt_outing_schema_for_activities, 'activities', 'listing')
outing_documents_config = GetDocumentsConfig(
    OUTING_TYPE, Outing, schema_outing,
    adapt_schema=outing_listing_schema_adaptor, set_custom_fields=set_author)


# route


def adapt_route_schema_for_activities(activities, field_list_type):
    """Get the schema for a set of activities.
    `field_list_type` should be either "fields" or "listing".
    """
    fields = get_all_fields(fields_route, activities, field_list_type)
    return restrict_schema(schema_route, fields)


route_schema_adaptor = make_schema_adaptor(
    adapt_route_schema_for_activities, 'activities', 'fields')
route_listing_schema_adaptor = make_schema_adaptor(
    adapt_route_schema_for_activities, 'activities', 'listing')

route_documents_config = GetDocumentsConfig(
    ROUTE_TYPE, Route, schema_route, clazz_locale=RouteLocale,
    adapt_schema=route_listing_schema_adaptor)


# topo map


topo_map_documents_config = GetDocumentsConfig(
    MAP_TYPE, TopoMap, schema_listing_topo_map)


# user profile


user_profile_documents_config = GetDocumentsConfig(
    USERPROFILE_TYPE, UserProfile, schema_listing_user_profile)


# waypoint


@lru_cache(maxsize=None)
def adapt_waypoint_schema_for_type(waypoint_type, field_list_type):
    """Get the schema for a waypoint type.
    `field_list_type` should be either "fields" or "listing".
    All schemas are cached using memoization with @lru_cache.
    """
    fields = fields_waypoint.get(waypoint_type).get(field_list_type)
    return restrict_schema(schema_waypoint, fields)


waypoint_schema_adaptor = make_schema_adaptor(
    adapt_waypoint_schema_for_type, 'waypoint_type', 'fields')
waypoint_listing_schema_adaptor = make_schema_adaptor(
    adapt_waypoint_schema_for_type, 'waypoint_type', 'listing')

waypoint_documents_config = GetDocumentsConfig(
    WAYPOINT_TYPE, Waypoint, schema_waypoint,
    adapt_schema=waypoint_listing_schema_adaptor)
