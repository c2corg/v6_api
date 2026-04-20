"""
Pydantic schemas for the Outing document type.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import (
    AccessConditions,
    Activities,
    AvalancheSigns,
    ClimbingRatings,
    ConditionRatings,
    EngagementRatings,
    EquipmentRatings,
    FrequentationTypes,
    GlacierRatings,
    GlobalRatings,
    HikingRatings,
    HutStatus,
    IceRatings,
    LiftStatus,
    MtbDownRatings,
    MtbUpRatings,
    QualityTypes,
    SkiRatings,
    SnowQualityRatings,
    SnowQuantityRatings,
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


class OutingLocaleSchema(DocumentLocaleSchema):
    """Outing locale — extends the base locale with outing-specific fields."""

    participants: Optional[str] = None
    access_comment: Optional[str] = None
    weather: Optional[str] = None
    timing: Optional[str] = None
    conditions_levels: Optional[str] = None
    conditions: Optional[str] = None
    avalanches: Optional[str] = None
    hut_comment: Optional[str] = None
    route_description: Optional[str] = None


class OutingDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full outing document schema for create and update requests.

    Fields mirror the SA model ``_OutingMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Outing-specific required fields --
    activities: List[Activities]
    date_start: date
    date_end: date

    # -- Outing-specific optional fields --
    frequentation: Optional[FrequentationTypes] = None
    participant_count: Optional[int] = None
    elevation_min: Optional[int] = None
    elevation_max: Optional[int] = None
    elevation_access: Optional[int] = None
    elevation_up_snow: Optional[int] = None
    elevation_down_snow: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_down: Optional[int] = None
    length_total: Optional[int] = None
    partial_trip: Optional[bool] = None
    public_transport: Optional[bool] = None
    access_condition: Optional[AccessConditions] = None
    lift_status: Optional[LiftStatus] = None
    condition_rating: Optional[ConditionRatings] = None
    snow_quantity: Optional[SnowQuantityRatings] = None
    snow_quality: Optional[SnowQualityRatings] = None
    glacier_rating: Optional[GlacierRatings] = None
    avalanche_signs: Optional[List[AvalancheSigns]] = None
    hut_status: Optional[HutStatus] = None
    disable_comments: Optional[bool] = None
    hiking_rating: Optional[HikingRatings] = None
    ski_rating: Optional[SkiRatings] = None
    labande_global_rating: Optional[GlobalRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    global_rating: Optional[GlobalRatings] = None
    height_diff_difficulties: Optional[int] = None
    engagement_rating: Optional[EngagementRatings] = None
    equipment_rating: Optional[EquipmentRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    ice_rating: Optional[IceRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None

    # -- Geometry --
    geometry: Optional[LineGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[OutingLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /outings)
# ---------------------------------------------------------------------------

CreateOutingSchema = OutingDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /outings/{id})
# ---------------------------------------------------------------------------


class UpdateOutingSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: OutingDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /outings/{id})
# ---------------------------------------------------------------------------


class OutingLocaleReadSchema(DocumentLocaleReadSchema):
    """Outing locale as returned in GET responses."""

    participants: Optional[str] = None
    access_comment: Optional[str] = None
    weather: Optional[str] = None
    timing: Optional[str] = None
    conditions_levels: Optional[str] = None
    conditions: Optional[str] = None
    avalanches: Optional[str] = None
    hut_comment: Optional[str] = None
    route_description: Optional[str] = None


class OutingReadSchema(DocumentReadSchema):
    """Full outing document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Outing`` instance.
    """

    activities: Optional[List[Activities]] = None
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    frequentation: Optional[FrequentationTypes] = None
    participant_count: Optional[int] = None
    elevation_min: Optional[int] = None
    elevation_max: Optional[int] = None
    elevation_access: Optional[int] = None
    elevation_up_snow: Optional[int] = None
    elevation_down_snow: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_down: Optional[int] = None
    length_total: Optional[int] = None
    partial_trip: Optional[bool] = None
    public_transport: Optional[bool] = None
    access_condition: Optional[AccessConditions] = None
    lift_status: Optional[LiftStatus] = None
    condition_rating: Optional[ConditionRatings] = None
    snow_quantity: Optional[SnowQuantityRatings] = None
    snow_quality: Optional[SnowQualityRatings] = None
    glacier_rating: Optional[GlacierRatings] = None
    avalanche_signs: Optional[List[AvalancheSigns]] = None
    hut_status: Optional[HutStatus] = None
    disable_comments: Optional[bool] = None
    hiking_rating: Optional[HikingRatings] = None
    ski_rating: Optional[SkiRatings] = None
    labande_global_rating: Optional[GlobalRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    global_rating: Optional[GlobalRatings] = None
    height_diff_difficulties: Optional[int] = None
    engagement_rating: Optional[EngagementRatings] = None
    equipment_rating: Optional[EquipmentRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    ice_rating: Optional[IceRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None

    geometry: Optional[LineGeometryReadSchema] = None
    locales: Optional[List[OutingLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None

    model_config = ConfigDict(extra='ignore')
