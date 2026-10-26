"""Schemas of the waypoints."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    LocaleSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Bool, Int, Map, OneOf, Seq, Str

WaypointGeometrySchema = geometry_schema(['POINT'])


class WaypointLocaleSchema(LocaleSchema):
    access: Str() = None
    access_period: Str() = None
    external_resources: Str() = None


class WaypointSchema(DocumentSchema):
    locales: Seq(WaypointLocaleSchema) = []
    geometry: Map(WaypointGeometrySchema) = None
    waypoint_type: OneOf(a.waypoint_types)
    elevation: Int = None
    prominence: Int = None
    length: Int = None
    height_median: Int = None
    elevation_min: Int = None
    routes_quantity: Int = None
    capacity: Int = None
    slope: Int = None
    height_max: Int = None
    capacity_staffed: Int = None
    climbing_outdoor_types: Seq(OneOf(a.climbing_outdoor_types)) = None
    climbing_indoor_types: Seq(OneOf(a.climbing_indoor_types)) = None
    public_transportation_types: Seq(OneOf(a.public_transportation_types)) = None
    product_types: Seq(OneOf(a.product_types)) = None
    ground_types: Seq(OneOf(a.ground_types)) = None
    weather_station_types: Seq(OneOf(a.weather_station_types)) = None
    rain_proof: OneOf(a.rain_proof_types) = None
    public_transportation_rating: OneOf(a.public_transportation_ratings) = None
    paragliding_rating: OneOf(a.paragliding_ratings) = None
    children_proof: OneOf(a.children_proof_types) = None
    snow_clearance_rating: OneOf(a.snow_clearance_ratings) = None
    exposition_rating: OneOf(a.exposition_ratings) = None
    rock_types: Seq(OneOf(a.rock_types)) = None
    orientations: Seq(OneOf(a.orientation_types)) = None
    best_periods: Seq(OneOf(a.months)) = None
    url: Str(255) = None
    maps_info: Str(300) = None
    phone: Str(50) = None
    lift_access: Bool = None
    phone_custodian: Str(50) = None
    custodianship: OneOf(a.custodianship_types) = None
    parking_fee: OneOf(a.parking_fee_types) = None
    matress_unstaffed: Bool = None
    blanket_unstaffed: Bool = None
    gas_unstaffed: Bool = None
    heating_unstaffed: Bool = None
    climbing_styles: Seq(OneOf(a.climbing_styles)) = None
    access_time: OneOf(a.access_times) = None
    climbing_rating_max: OneOf(a.climbing_ratings) = None
    climbing_rating_min: OneOf(a.climbing_ratings) = None
    climbing_rating_median: OneOf(a.climbing_ratings) = None
    height_min: Int = None
    equipment_ratings: Seq(OneOf(a.equipment_ratings)) = None
    slackline_types: Seq(OneOf(a.slackline_types)) = None
    slackline_length_min: Int = None
    slackline_length_max: Int = None


WaypointCreateSchema = create_schema(WaypointSchema, AssociationsSchema)
WaypointUpdateSchema = update_schema(WaypointCreateSchema)

waypoint_schema = ModelSchema(
    Waypoint,
    WaypointSchema,
    document_children(
        locale_schema=WaypointLocaleSchema,
        locale_model=WaypointLocale,
        geometry=WaypointGeometrySchema,
    ),
)
