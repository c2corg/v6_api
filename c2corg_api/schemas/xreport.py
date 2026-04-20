"""
Pydantic schemas for the Xreport (incident/accident report) document type.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import (
    ActivityRates,
    AuthorStatuses,
    Autonomies,
    AvalancheLevels,
    AvalancheSlopes,
    EventActivities,
    EventTypes,
    Genders,
    PreviousInjuries,
    Qualification,
    QualityTypes,
    Severities,
    Supervision,
)
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    PointGeometryReadSchema,
    PointGeometrySchema,
)


class XreportLocaleSchema(DocumentLocaleSchema):
    """Xreport locale — extends the base locale with incident-report fields."""

    place: Optional[str] = None
    route_study: Optional[str] = None
    conditions: Optional[str] = None
    training: Optional[str] = None
    motivations: Optional[str] = None
    group_management: Optional[str] = None
    risk: Optional[str] = None
    time_management: Optional[str] = None
    safety: Optional[str] = None
    reduce_impact: Optional[str] = None
    increase_impact: Optional[str] = None
    modifications: Optional[str] = None
    other_comments: Optional[str] = None


class XreportDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full xreport document schema for create and update requests.

    Fields mirror the SA model ``_XreportMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Xreport-specific fields --
    elevation: Optional[int] = None
    date: Optional[datetime.date] = None
    event_type: Optional[EventTypes] = None
    event_activity: EventActivities  # required
    nb_participants: Optional[int] = None
    nb_impacted: Optional[int] = None
    rescue: Optional[bool] = None
    avalanche_level: Optional[AvalancheLevels] = None
    avalanche_slope: Optional[AvalancheSlopes] = None
    severity: Optional[Severities] = None
    author_status: Optional[AuthorStatuses] = None
    activity_rate: Optional[ActivityRates] = None
    age: Optional[int] = None
    gender: Optional[Genders] = None
    previous_injuries: Optional[PreviousInjuries] = None
    autonomy: Optional[Autonomies] = None
    supervision: Optional[Supervision] = None
    qualification: Optional[Qualification] = None
    disable_comments: Optional[bool] = None
    anonymous: Optional[bool] = None

    # -- Geometry --
    geometry: Optional[PointGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[XreportLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /xreports)
# ---------------------------------------------------------------------------

CreateXreportSchema = XreportDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /xreports/{id})
# ---------------------------------------------------------------------------


class UpdateXreportSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: XreportDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /xreports/{id})
# ---------------------------------------------------------------------------


class XreportLocaleReadSchema(DocumentLocaleReadSchema):
    """Xreport locale as returned in GET responses."""

    place: Optional[str] = None
    route_study: Optional[str] = None
    conditions: Optional[str] = None
    training: Optional[str] = None
    motivations: Optional[str] = None
    group_management: Optional[str] = None
    risk: Optional[str] = None
    time_management: Optional[str] = None
    safety: Optional[str] = None
    reduce_impact: Optional[str] = None
    increase_impact: Optional[str] = None
    modifications: Optional[str] = None
    other_comments: Optional[str] = None


class XreportReadSchema(DocumentReadSchema):
    """Full xreport document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Xreport`` instance.

    Personal fields (``age``, ``gender``, etc.) are included; the view layer
    is responsible for stripping them via ``schema_xreport_without_personal``
    for non-authorized users (unchanged from the current behaviour).
    """

    elevation: Optional[int] = None
    date: Optional[datetime.date] = None
    event_type: Optional[EventTypes] = None
    event_activity: Optional[EventActivities] = None
    nb_participants: Optional[int] = None
    nb_impacted: Optional[int] = None
    rescue: Optional[bool] = None
    avalanche_level: Optional[AvalancheLevels] = None
    avalanche_slope: Optional[AvalancheSlopes] = None
    severity: Optional[Severities] = None
    author_status: Optional[AuthorStatuses] = None
    activity_rate: Optional[ActivityRates] = None
    age: Optional[int] = None
    gender: Optional[Genders] = None
    previous_injuries: Optional[PreviousInjuries] = None
    autonomy: Optional[Autonomies] = None
    supervision: Optional[Supervision] = None
    qualification: Optional[Qualification] = None
    disable_comments: Optional[bool] = None
    anonymous: Optional[bool] = None

    geometry: Optional[PointGeometryReadSchema] = None
    locales: Optional[List[XreportLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
