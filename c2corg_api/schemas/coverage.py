"""
Pydantic schemas for the Coverage (Navitia coverage) document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import CoverageTypes, QualityTypes
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    StrictPolygonGeometryReadSchema,
    StrictPolygonGeometrySchema,
)


class CoverageDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full coverage document schema for create and update requests.

    Fields mirror the SA model ``_CoverageMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Coverage-specific fields --
    coverage_type: Optional[CoverageTypes] = None

    # -- Geometry --
    geometry: Optional[StrictPolygonGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /coverages)
# ---------------------------------------------------------------------------

CreateCoverageSchema = CoverageDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /coverages/{id})
# ---------------------------------------------------------------------------


class UpdateCoverageSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: CoverageDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /coverages/{id})
# ---------------------------------------------------------------------------


class CoverageReadSchema(DocumentReadSchema):
    """Full coverage document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Coverage`` instance.
    """

    coverage_type: Optional[CoverageTypes] = None

    geometry: Optional[StrictPolygonGeometryReadSchema] = None
    locales: Optional[List[DocumentLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
