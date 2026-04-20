"""
Pydantic schemas for the TopoMap document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import MapEditors, MapScales, QualityTypes
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    PolygonGeometrySchema,
    StrictPolygonGeometryReadSchema,
)


class TopoMapDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full topo-map document schema for create and update requests.

    Fields mirror the SA model ``_MapMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Map-specific fields --
    editor: Optional[MapEditors] = None
    scale: Optional[MapScales] = None
    code: Optional[str] = None

    # -- Geometry --
    geometry: Optional[PolygonGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /maps)
# ---------------------------------------------------------------------------

CreateTopoMapSchema = TopoMapDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /maps/{id})
# ---------------------------------------------------------------------------


class UpdateTopoMapSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: TopoMapDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /maps/{id})
# ---------------------------------------------------------------------------


class TopoMapReadSchema(DocumentReadSchema):
    """Full topo-map document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``TopoMap`` instance.
    """

    editor: Optional[MapEditors] = None
    scale: Optional[MapScales] = None
    code: Optional[str] = None

    geometry: Optional[StrictPolygonGeometryReadSchema] = None
    locales: Optional[List[DocumentLocaleReadSchema]] = None

    redirects_to: Optional[int] = None
    cooked: Optional[dict] = None
