"""Schemas of the outings."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    LocaleSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Bool, Date, Int, Map, OneOf, Seq, Str

OutingGeometrySchema = geometry_schema(['LINESTRING', 'MULTILINESTRING'])


class OutingLocaleSchema(LocaleSchema):
    access_comment: Str() = None
    avalanches: Str() = None
    conditions: Str() = None
    conditions_levels: Str() = None
    hut_comment: Str() = None
    participants: Str() = None
    route_description: Str() = None
    timing: Str() = None
    weather: Str() = None


class OutingSchema(DocumentSchema):
    locales: Seq(OutingLocaleSchema) = []
    geometry: Map(OutingGeometrySchema) = None
    access_condition: OneOf(a.access_conditions) = None
    # as with Colander, the items of activities and avalanche_signs are not
    # checked against their enum here
    activities: Seq(Str(), min_length=1)
    avalanche_signs: Seq(Str()) = None
    condition_rating: OneOf(a.condition_ratings) = None
    date_end: Date
    date_start: Date
    elevation_access: Int = None
    elevation_down_snow: Int = None
    elevation_max: Int = None
    elevation_min: Int = None
    elevation_up_snow: Int = None
    frequentation: OneOf(a.frequentation_types) = None
    glacier_rating: OneOf(a.glacier_ratings) = None
    height_diff_down: Int = None
    height_diff_up: Int = None
    hut_status: OneOf(a.hut_status) = None
    length_total: Int = None
    lift_status: OneOf(a.lift_status) = None
    partial_trip: Bool = None
    participant_count: Int = None
    public_transport: Bool = None
    snow_quality: OneOf(a.condition_ratings) = None
    snow_quantity: OneOf(a.condition_ratings) = None
    disable_comments: Bool = None
    hiking_rating: OneOf(a.hiking_ratings) = None
    ski_rating: OneOf(a.ski_ratings) = None
    labande_global_rating: OneOf(a.global_ratings) = None
    ice_rating: OneOf(a.ice_ratings) = None
    snowshoe_rating: OneOf(a.snowshoe_ratings) = None
    global_rating: OneOf(a.global_ratings) = None
    height_diff_difficulties: Int = None
    engagement_rating: OneOf(a.engagement_ratings) = None
    equipment_rating: OneOf(a.equipment_ratings) = None
    rock_free_rating: OneOf(a.climbing_ratings) = None
    via_ferrata_rating: OneOf(a.via_ferrata_ratings) = None
    mtb_up_rating: OneOf(a.mtb_up_ratings) = None
    mtb_down_rating: OneOf(a.mtb_down_ratings) = None


OutingCreateSchema = create_schema(OutingSchema, AssociationsSchema)
OutingUpdateSchema = update_schema(OutingCreateSchema)

outing_schema = ModelSchema(
    Outing,
    OutingSchema,
    document_children(
        locale_schema=OutingLocaleSchema,
        locale_model=OutingLocale,
        geometry=OutingGeometrySchema,
    ),
)
