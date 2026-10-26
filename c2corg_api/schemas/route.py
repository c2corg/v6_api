"""Schemas of the routes."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    LocaleSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Bool, Float, Int, Map, OneOf, Seq, Str

RouteGeometrySchema = geometry_schema(['LINESTRING', 'MULTILINESTRING'])


class RouteLocaleSchema(LocaleSchema):
    slope: Str() = None
    remarks: Str() = None
    gear: Str() = None
    external_resources: Str() = None
    route_history: Str() = None
    slackline_anchor1: Str() = None
    slackline_anchor2: Str() = None
    # set from the title of the main waypoint
    title_prefix: Str() = None


class RouteSchema(DocumentSchema):
    locales: Seq(RouteLocaleSchema) = []
    geometry: Map(RouteGeometrySchema) = None
    main_waypoint_id: Int = None
    # as with Colander, the items of the lists are not checked against their
    # enum here
    activities: Seq(Str(), min_length=1)
    elevation_min: Int = None
    elevation_max: Int = None
    height_diff_up: Int = None
    height_diff_down: Int = None
    route_length: Int = None
    durations: Seq(Str()) = None
    calculated_duration: Float = None
    difficulties_height: Int = None
    height_diff_access: Int = None
    height_diff_difficulties: Int = None
    route_types: Seq(Str()) = None
    orientations: Seq(Str()) = None
    glacier_gear: OneOf(a.glacier_gear_types) = 'no'
    configuration: Seq(Str()) = None
    lift_access: Bool = None
    ski_rating: OneOf(a.ski_ratings) = None
    ski_exposition: OneOf(a.exposition_ratings) = None
    labande_ski_rating: OneOf(a.labande_ski_ratings) = None
    labande_global_rating: OneOf(a.global_ratings) = None
    global_rating: OneOf(a.global_ratings) = None
    engagement_rating: OneOf(a.engagement_ratings) = None
    risk_rating: OneOf(a.risk_ratings) = None
    equipment_rating: OneOf(a.equipment_ratings) = None
    ice_rating: OneOf(a.ice_ratings) = None
    mixed_rating: OneOf(a.mixed_ratings) = None
    exposition_rock_rating: OneOf(a.exposition_rock_ratings) = None
    rock_free_rating: OneOf(a.climbing_ratings) = None
    rock_required_rating: OneOf(a.climbing_ratings) = None
    aid_rating: OneOf(a.aid_ratings) = None
    via_ferrata_rating: OneOf(a.via_ferrata_ratings) = None
    hiking_rating: OneOf(a.hiking_ratings) = None
    hiking_mtb_exposition: OneOf(a.exposition_ratings) = None
    snowshoe_rating: OneOf(a.snowshoe_ratings) = None
    mtb_up_rating: OneOf(a.mtb_up_ratings) = None
    mtb_down_rating: OneOf(a.mtb_down_ratings) = None
    mtb_length_asphalt: Int = None
    mtb_length_trail: Int = None
    mtb_height_diff_portages: Int = None
    rock_types: Seq(Str()) = None
    climbing_outdoor_type: OneOf(a.climbing_outdoor_types) = None
    slackline_type: OneOf(a.slackline_types) = None
    slackline_height: Int = None
    public_transportation_rating: OneOf(a.public_transportation_ratings) = None


RouteCreateSchema = create_schema(RouteSchema, AssociationsSchema)
RouteUpdateSchema = update_schema(RouteCreateSchema)

route_schema = ModelSchema(
    Route,
    RouteSchema,
    document_children(
        locale_schema=RouteLocaleSchema,
        locale_model=RouteLocale,
        geometry=RouteGeometrySchema,
    ),
)
