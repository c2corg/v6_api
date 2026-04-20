"""
Pydantic schemas for the Area document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import AreaTypes, QualityTypes
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    PolygonGeometryReadSchema,
    PolygonGeometrySchema,
)


class AreaDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full area document schema for create and update requests.

    Fields mirror the SA model ``_AreaMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Area-specific fields --
    area_type: Optional[AreaTypes] = None

    # -- Geometry --
    geometry: Optional[PolygonGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /areas)
# ---------------------------------------------------------------------------

CreateAreaSchema = AreaDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /areas/{id})
# ---------------------------------------------------------------------------


class UpdateAreaSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: AreaDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /areas/{id})
# ---------------------------------------------------------------------------


class AreaReadSchema(DocumentReadSchema):
    """Full area document schema for GET responses.

    Areas use a plain ``DocumentLocaleReadSchema`` (no type-specific locale
    fields beyond the base).
    """

    area_type: Optional[AreaTypes] = None

    geometry: Optional[PolygonGeometryReadSchema] = None
    locales: Optional[List[DocumentLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
