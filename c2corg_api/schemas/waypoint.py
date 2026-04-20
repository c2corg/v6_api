"""
Pydantic schemas for the Waypoint document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import (
    AccessTimes,
    ChildrenProofTypes,
    ClimbingIndoorTypes,
    ClimbingOutdoorTypes,
    ClimbingRatings,
    ClimbingStyles,
    CustodianshipTypes,
    EquipmentRatings,
    ExpositionRatings,
    GroundTypes,
    Months,
    OrientationTypes,
    ParaglidingRatings,
    ParkingFeeTypes,
    ProductTypes,
    PublicTransportationRatings,
    PublicTransportationTypes,
    QualityTypes,
    RainProofTypes,
    RockTypes,
    SlacklineTypes,
    SnowClearanceRatings,
    WaypointTypes,
    WeatherStationTypes,
)
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    WaypointGeometryReadSchema,
    WaypointGeometrySchema,
)


class WaypointLocaleSchema(DocumentLocaleSchema):
    """Waypoint locale — extends the base locale with access fields."""

    access: Optional[str] = None
    access_period: Optional[str] = None
    external_resources: Optional[str] = None


class WaypointDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full waypoint document schema for create and update requests.

    Fields mirror the SA model ``_WaypointMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Waypoint-specific fields --
    waypoint_type: Optional[WaypointTypes] = None
    elevation: Optional[int] = None
    elevation_min: Optional[int] = None
    prominence: Optional[int] = None
    height_max: Optional[int] = None
    height_median: Optional[int] = None
    height_min: Optional[int] = None
    routes_quantity: Optional[int] = None
    climbing_outdoor_types: Optional[List[ClimbingOutdoorTypes]] = None
    climbing_indoor_types: Optional[List[ClimbingIndoorTypes]] = None
    climbing_rating_max: Optional[ClimbingRatings] = None
    climbing_rating_min: Optional[ClimbingRatings] = None
    climbing_rating_median: Optional[ClimbingRatings] = None
    equipment_ratings: Optional[List[EquipmentRatings]] = None
    climbing_styles: Optional[List[ClimbingStyles]] = None
    children_proof: Optional[ChildrenProofTypes] = None
    rain_proof: Optional[RainProofTypes] = None
    orientations: Optional[List[OrientationTypes]] = None
    best_periods: Optional[List[Months]] = None
    product_types: Optional[List[ProductTypes]] = None
    length: Optional[int] = None
    slope: Optional[int] = None
    ground_types: Optional[List[GroundTypes]] = None
    paragliding_rating: Optional[ParaglidingRatings] = None
    exposition_rating: Optional[ExpositionRatings] = None
    rock_types: Optional[List[RockTypes]] = None
    weather_station_types: Optional[List[WeatherStationTypes]] = None
    url: Optional[str] = None
    maps_info: Optional[str] = None
    phone: Optional[str] = None
    public_transportation_types: Optional[List[PublicTransportationTypes]] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None
    snow_clearance_rating: Optional[SnowClearanceRatings] = None
    lift_access: Optional[bool] = None
    parking_fee: Optional[ParkingFeeTypes] = None
    phone_custodian: Optional[str] = None
    custodianship: Optional[CustodianshipTypes] = None
    matress_unstaffed: Optional[bool] = None
    blanket_unstaffed: Optional[bool] = None
    gas_unstaffed: Optional[bool] = None
    heating_unstaffed: Optional[bool] = None
    access_time: Optional[AccessTimes] = None
    capacity: Optional[int] = None
    capacity_staffed: Optional[int] = None
    slackline_types: Optional[List[SlacklineTypes]] = None
    slackline_length_min: Optional[int] = None
    slackline_length_max: Optional[int] = None

    # -- Geometry --
    geometry: Optional[WaypointGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[WaypointLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /waypoints)
# ---------------------------------------------------------------------------

CreateWaypointSchema = WaypointDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /waypoints/{id})
# ---------------------------------------------------------------------------


class UpdateWaypointSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: WaypointDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /waypoints/{id})
# ---------------------------------------------------------------------------


class WaypointLocaleReadSchema(DocumentLocaleReadSchema):
    """Waypoint locale as returned in GET responses."""

    access: Optional[str] = None
    access_period: Optional[str] = None
    external_resources: Optional[str] = None


class WaypointReadSchema(DocumentReadSchema):
    """Full waypoint document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Waypoint`` instance —
    ready for use as a FastAPI ``response_model``.
    """

    waypoint_type: Optional[WaypointTypes] = None
    elevation: Optional[int] = None
    elevation_min: Optional[int] = None
    prominence: Optional[int] = None
    height_max: Optional[int] = None
    height_median: Optional[int] = None
    height_min: Optional[int] = None
    routes_quantity: Optional[int] = None
    climbing_outdoor_types: Optional[List[ClimbingOutdoorTypes]] = None
    climbing_indoor_types: Optional[List[ClimbingIndoorTypes]] = None
    climbing_rating_max: Optional[ClimbingRatings] = None
    climbing_rating_min: Optional[ClimbingRatings] = None
    climbing_rating_median: Optional[ClimbingRatings] = None
    equipment_ratings: Optional[List[EquipmentRatings]] = None
    climbing_styles: Optional[List[ClimbingStyles]] = None
    children_proof: Optional[ChildrenProofTypes] = None
    rain_proof: Optional[RainProofTypes] = None
    orientations: Optional[List[OrientationTypes]] = None
    best_periods: Optional[List[Months]] = None
    product_types: Optional[List[ProductTypes]] = None
    length: Optional[int] = None
    slope: Optional[int] = None
    ground_types: Optional[List[GroundTypes]] = None
    paragliding_rating: Optional[ParaglidingRatings] = None
    exposition_rating: Optional[ExpositionRatings] = None
    rock_types: Optional[List[RockTypes]] = None
    weather_station_types: Optional[List[WeatherStationTypes]] = None
    url: Optional[str] = None
    maps_info: Optional[str] = None
    phone: Optional[str] = None
    public_transportation_types: Optional[List[PublicTransportationTypes]] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None
    snow_clearance_rating: Optional[SnowClearanceRatings] = None
    lift_access: Optional[bool] = None
    parking_fee: Optional[ParkingFeeTypes] = None
    phone_custodian: Optional[str] = None
    custodianship: Optional[CustodianshipTypes] = None
    matress_unstaffed: Optional[bool] = None
    blanket_unstaffed: Optional[bool] = None
    gas_unstaffed: Optional[bool] = None
    heating_unstaffed: Optional[bool] = None
    access_time: Optional[AccessTimes] = None
    capacity: Optional[int] = None
    capacity_staffed: Optional[int] = None
    slackline_types: Optional[List[SlacklineTypes]] = None
    slackline_length_min: Optional[int] = None
    slackline_length_max: Optional[int] = None

    geometry: Optional[WaypointGeometryReadSchema] = None
    locales: Optional[List[WaypointLocaleReadSchema]] = None

    redirects_to: Optional[int] = None
    cooked: Optional[dict] = None
