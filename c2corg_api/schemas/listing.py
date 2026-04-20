"""
Listing schemas — lightweight Pydantic schemas that produce the same
output as ``to_json_dict(obj, schema_listing_*)`` for each document type.

**Option A strategy**: each schema declares the *union* of all possible
listing fields for that document type (across all activity types /
waypoint types).  ``model_dump(exclude_none=True)`` omits keys whose
value is ``None``, producing output equivalent to the old
``to_json_dict`` + ``adapt_schema`` pattern.
"""

from datetime import date as date_type
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_serializer

from c2corg_api.models.common.attributes import (
    Activities,
    AidRatings,
    AreaTypes,
    ClimbingOutdoorTypes,
    ClimbingRatings,
    ConditionRatings,
    CoverageTypes,
    DefaultLangs,
    EngagementRatings,
    EquipmentRatings,
    ExpositionRatings,
    GlobalRatings,
    HikingRatings,
    IceRatings,
    LabandeSkiRatings,
    MapEditors,
    MixedRatings,
    MtbDownRatings,
    MtbUpRatings,
    OrientationTypes,
    PublicTransportationRatings,
    QualityTypes,
    RiskRatings,
    RouteDurationTypes,
    SkiRatings,
    SlacklineTypes,
    SnowshoeRatings,
    UserCategories,
    ViaFerrataRatings,
    WaypointTypes,
)

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class _ListingBase(BaseModel):
    """Common fields for every listing schema."""

    document_id: int
    version: Optional[int] = None
    type: Optional[str] = None
    protected: Optional[bool] = None
    available_langs: Optional[List[str]] = None
    img_count: Optional[int] = None
    creator: Optional[Any] = None
    author: Optional[Any] = None
    name: Optional[str] = None
    forum_username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


# ---------------------------------------------------------------------------
# Listing locale variants
# ---------------------------------------------------------------------------


class ListingLocaleSchema(BaseModel):
    """lang + version + title only."""

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class ListingLocaleSummarySchema(BaseModel):
    """+ summary."""

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None
    summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class RouteListingLocaleSchema(BaseModel):
    """+ title_prefix + summary."""

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None
    title_prefix: Optional[str] = None
    summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class WaypointListingLocaleSchema(BaseModel):
    """+ summary + access_period."""

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    access_period: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


# ---------------------------------------------------------------------------
# Listing geometry
# ---------------------------------------------------------------------------


class ListingPointGeometrySchema(BaseModel):
    """geom (POINT) + has_geom_detail."""

    version: Optional[int] = None
    geom: Optional[Any] = None
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')

    @field_serializer('geom')
    @classmethod
    def _serialize_geom(cls, v: Any) -> Any:
        from c2corg_api.schemas.geometry import wkbelement_to_geojson_str

        return wkbelement_to_geojson_str(v)


class ListingPolygonGeometrySchema(BaseModel):
    """geom_detail only (coverage)."""

    version: Optional[int] = None
    geom_detail: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')

    @field_serializer('geom_detail')
    @classmethod
    def _serialize_geom_detail(cls, v: Any) -> Any:
        from c2corg_api.schemas.geometry import wkbelement_to_geojson_str

        return wkbelement_to_geojson_str(v)


# =========================================================================
# Per-type listing schemas
# =========================================================================


class AreaListingSchema(_ListingBase):
    area_type: Optional[AreaTypes] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class ArticleListingSchema(_ListingBase):
    categories: Optional[List[str]] = None
    activities: Optional[List[Activities]] = None
    article_type: Optional[str] = None
    quality: Optional[QualityTypes] = None
    locales: Optional[List[ListingLocaleSummarySchema]] = None


class BookListingSchema(_ListingBase):
    activities: Optional[List[Activities]] = None
    book_types: Optional[List[str]] = None
    quality: Optional[QualityTypes] = None
    locales: Optional[List[ListingLocaleSummarySchema]] = None


class CoverageListingSchema(_ListingBase):
    coverage_type: Optional[CoverageTypes] = None
    geometry: Optional[ListingPolygonGeometrySchema] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class ImageListingSchema(_ListingBase):
    filename: Optional[str] = None
    geometry: Optional[ListingPointGeometrySchema] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class TopoMapListingSchema(_ListingBase):
    code: Optional[str] = None
    editor: Optional[MapEditors] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class UserProfileListingSchema(_ListingBase):
    categories: Optional[List[UserCategories]] = None
    activities: Optional[List[Activities]] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class XreportListingSchema(_ListingBase):
    elevation: Optional[int] = None
    date: Optional[date_type] = None
    event_type: Optional[str] = None
    event_activity: Optional[str] = None
    nb_participants: Optional[int] = None
    nb_impacted: Optional[int] = None
    avalanche_level: Optional[str] = None
    avalanche_slope: Optional[str] = None
    severity: Optional[str] = None
    quality: Optional[QualityTypes] = None
    geometry: Optional[ListingPointGeometrySchema] = None
    locales: Optional[List[ListingLocaleSchema]] = None


class OutingListingSchema(_ListingBase):
    """Union of all outing listing fields across activities."""

    activities: Optional[List[Activities]] = None
    date_start: Optional[date_type] = None
    date_end: Optional[date_type] = None
    elevation_max: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_difficulties: Optional[int] = None
    public_transport: Optional[bool] = None
    condition_rating: Optional[ConditionRatings] = None
    quality: Optional[QualityTypes] = None
    ski_rating: Optional[SkiRatings] = None
    labande_global_rating: Optional[GlobalRatings] = None
    global_rating: Optional[GlobalRatings] = None
    engagement_rating: Optional[EngagementRatings] = None
    equipment_rating: Optional[EquipmentRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    ice_rating: Optional[IceRatings] = None
    hiking_rating: Optional[HikingRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    geometry: Optional[ListingPointGeometrySchema] = None
    locales: Optional[List[ListingLocaleSummarySchema]] = None


class RouteListingSchema(_ListingBase):
    """Union of all route listing fields across activities."""

    activities: Optional[List[Activities]] = None
    elevation_max: Optional[int] = None
    elevation_min: Optional[int] = None
    height_diff_up: Optional[int] = None
    height_diff_down: Optional[int] = None
    height_diff_difficulties: Optional[int] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None
    quality: Optional[QualityTypes] = None
    orientations: Optional[List[OrientationTypes]] = None
    durations: Optional[List[RouteDurationTypes]] = None
    calculated_duration: Optional[float] = None
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
    exposition_rock_rating: Optional[ExpositionRatings] = None
    rock_free_rating: Optional[ClimbingRatings] = None
    rock_required_rating: Optional[ClimbingRatings] = None
    aid_rating: Optional[AidRatings] = None
    hiking_rating: Optional[HikingRatings] = None
    hiking_mtb_exposition: Optional[ExpositionRatings] = None
    snowshoe_rating: Optional[SnowshoeRatings] = None
    mtb_up_rating: Optional[MtbUpRatings] = None
    mtb_down_rating: Optional[MtbDownRatings] = None
    via_ferrata_rating: Optional[ViaFerrataRatings] = None
    climbing_outdoor_type: Optional[ClimbingOutdoorTypes] = None
    slackline_type: Optional[SlacklineTypes] = None
    slackline_height: Optional[int] = None
    route_length: Optional[int] = None
    geometry: Optional[ListingPointGeometrySchema] = None
    locales: Optional[List[RouteListingLocaleSchema]] = None


class WaypointListingSchema(_ListingBase):
    """Union of all waypoint listing fields across types."""

    waypoint_type: Optional[WaypointTypes] = None
    elevation: Optional[int] = None
    quality: Optional[QualityTypes] = None
    public_transportation_rating: Optional[PublicTransportationRatings] = None
    slackline_types: Optional[List[SlacklineTypes]] = None
    slackline_length_min: Optional[int] = None
    slackline_length_max: Optional[int] = None
    geometry: Optional[ListingPointGeometrySchema] = None
    locales: Optional[List[WaypointListingLocaleSchema]] = None


# =========================================================================
# Lookup: document_type → listing schema class
# =========================================================================

LISTING_SCHEMA_MAP: dict[str, type[_ListingBase]] = {
    'a': AreaListingSchema,
    'c': ArticleListingSchema,
    'b': BookListingSchema,
    'v': CoverageListingSchema,
    'i': ImageListingSchema,
    'm': TopoMapListingSchema,
    'u': UserProfileListingSchema,
    'x': XreportListingSchema,
    'o': OutingListingSchema,
    'r': RouteListingSchema,
    'w': WaypointListingSchema,
}
