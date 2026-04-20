"""
Pydantic schemas for the Route document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import (
    Activities,
    AidRatings,
    ClimbingOutdoorTypes,
    ClimbingRatings,
    EngagementRatings,
    EquipmentRatings,
    ExpositionRatings,
    ExpositionRockRatings,
    GlacierGearTypes,
    GlobalRatings,
    HikingRatings,
    IceRatings,
    LabandeSkiRatings,
    MixedRatings,
    MtbDownRatings,
    MtbUpRatings,
    OrientationTypes,
    PublicTransportationRatings,
    QualityTypes,
    RiskRatings,
    RockTypes,
    RouteConfigurationTypes,
    RouteDurationTypes,
    RouteTypes,
    SkiRatings,
    SlacklineTypes,
    SnowshoeRatings,
    ViaFerrataRatings,
)
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    LineGeometryReadSchema,
    LineGeometrySchema,
)


class RouteLocaleSchema(DocumentLocaleSchema):
    """Route locale — extends the base locale with route-specific text fields.

    ``title_prefix`` is the cached title of the main waypoint; it is
    accepted on input but silently overwritten by the backend.
    """

    slope: Optional[str] = None
    remarks: Optional[str] = None
    gear: Optional[str] = None
    external_resources: Optional[str] = None
    route_history: Optional[str] = None
    slackline_anchor1: Optional[str] = None
    slackline_anchor2: Optional[str] = None
    title_prefix: Optional[str] = None


class RouteDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full route document schema for create and update requests.

    Fields mirror ``_RouteMixin`` + ``Route`` + ``Document`` base columns.
    Routes use ``LineGeometrySchema`` (POINT + LINESTRING/MULTILINESTRING).
    """

    # -- Document base fields --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Route-specific fields --
    main_waypoint_id: Optional[int] = None
    activities: Optional[List[Activities]] = None
    elevation_min: Optional[int] = None
    elevation_max: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_down: Optional[int] = None
    route_length: Optional[int] = None
    durations: Optional[List[RouteDurationTypes]] = None
    calculated_duration: Optional[float] = None
    difficulties_height: Optional[int] = None
    height_diff_access: Optional[int] = None
    height_diff_difficulties: Optional[int] = None
    route_types: Optional[List[RouteTypes]] = None
    orientations: Optional[List[OrientationTypes]] = None
    glacier_gear: Optional[GlacierGearTypes] = GlacierGearTypes.no
    configuration: Optional[List[RouteConfigurationTypes]] = None
    lift_access: Optional[bool] = None
    ski_rating: Optional[SkiRatings] = None
    ski_exposition: Optional[ExpositionRatings] = None
    labande_ski_rating: Optional[LabandeSkiRatings] = None
    labande_global_rating: Optional[GlobalRatings] = None
    global_rating: Optional[GlobalRatings] = None
    engagement_rating: Optional[EngagementRatings] = None
    risk_rating: Optional[RiskRatings] = None
    equipment_rating: Optional[EquipmentRatings] = None
    ice_rating: Optional[IceRatings] = None
    mixed_rating: Optional[MixedRatings] = None
    exposition_rock_rating: Optional[ExpositionRockRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    rock_required_rating: Optional[ClimbingRatings] = None
    aid_rating: Optional[AidRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    hiking_rating: Optional[HikingRatings] = None
    hiking_mtb_exposition: Optional[ExpositionRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None
    mtb_length_asphalt: Optional[int] = None
    mtb_length_trail: Optional[int] = None
    mtb_height_diff_portages: Optional[int] = None
    rock_types: Optional[List[RockTypes]] = None
    climbing_outdoor_type: Optional[ClimbingOutdoorTypes] = None
    slackline_type: Optional[SlacklineTypes] = None
    slackline_height: Optional[int] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None

    # -- Nested objects --
    locales: Optional[List[RouteLocaleSchema]] = None
    geometry: Optional[LineGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (PUT /routes)
# ---------------------------------------------------------------------------

CreateRouteSchema = RouteDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /routes/{id})
# ---------------------------------------------------------------------------


class UpdateRouteSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: RouteDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /routes/{id})
# ---------------------------------------------------------------------------


class RouteLocaleReadSchema(DocumentLocaleReadSchema):
    """Route locale as returned in GET responses."""

    slope: Optional[str] = None
    remarks: Optional[str] = None
    gear: Optional[str] = None
    external_resources: Optional[str] = None
    route_history: Optional[str] = None
    slackline_anchor1: Optional[str] = None
    slackline_anchor2: Optional[str] = None
    title_prefix: Optional[str] = None


class RouteReadSchema(DocumentReadSchema):
    """Full route document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Route`` instance.
    The geometry carries ``has_geom_detail`` to indicate whether a detailed
    track is stored.
    """

    main_waypoint_id: Optional[int] = None
    activities: Optional[List[Activities]] = None
    elevation_min: Optional[int] = None
    elevation_max: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_down: Optional[int] = None
    route_length: Optional[int] = None
    durations: Optional[List[RouteDurationTypes]] = None
    calculated_duration: Optional[float] = None
    difficulties_height: Optional[int] = None
    height_diff_access: Optional[int] = None
    height_diff_difficulties: Optional[int] = None
    route_types: Optional[List[RouteTypes]] = None
    orientations: Optional[List[OrientationTypes]] = None
    glacier_gear: Optional[GlacierGearTypes] = None
    configuration: Optional[List[RouteConfigurationTypes]] = None
    lift_access: Optional[bool] = None
    ski_rating: Optional[SkiRatings] = None
    ski_exposition: Optional[ExpositionRatings] = None
    labande_ski_rating: Optional[LabandeSkiRatings] = None
    labande_global_rating: Optional[GlobalRatings] = None
    global_rating: Optional[GlobalRatings] = None
    engagement_rating: Optional[EngagementRatings] = None
    risk_rating: Optional[RiskRatings] = None
    equipment_rating: Optional[EquipmentRatings] = None
    ice_rating: Optional[IceRatings] = None
    mixed_rating: Optional[MixedRatings] = None
    exposition_rock_rating: Optional[ExpositionRockRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    rock_required_rating: Optional[ClimbingRatings] = None
    aid_rating: Optional[AidRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    hiking_rating: Optional[HikingRatings] = None
    hiking_mtb_exposition: Optional[ExpositionRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None
    mtb_length_asphalt: Optional[int] = None
    mtb_length_trail: Optional[int] = None
    mtb_height_diff_portages: Optional[int] = None
    rock_types: Optional[List[RockTypes]] = None
    climbing_outdoor_type: Optional[ClimbingOutdoorTypes] = None
    slackline_type: Optional[SlacklineTypes] = None
    slackline_height: Optional[int] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None

    geometry: Optional[LineGeometryReadSchema] = None
    locales: Optional[List[RouteLocaleReadSchema]] = None

    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
