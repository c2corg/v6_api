"""
Pydantic schemas for the Image document type.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from c2corg_api.models.common.attributes import (
    Activities,
    ImageCategories,
    ImageTypes,
    QualityTypes,
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

# ---------------------------------------------------------------------------
# Image-specific locale
# ---------------------------------------------------------------------------


class ImageLocaleSchema(DocumentLocaleSchema):
    """Image locales: images can be created without a title."""

    title: Optional[str] = ''

    @field_validator('title', mode='before')
    @classmethod
    def _coerce_none_title(cls, v):
        """``None`` / absent title becomes the empty string."""
        if v is None:
            return ''
        return v


class ImageDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full image document schema for create and update requests.

    Fields mirror the SA model ``_ImageMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Image-specific fields --
    activities: Optional[List[Activities]] = None
    categories: Optional[List[ImageCategories]] = None
    image_type: Optional[ImageTypes] = None
    author: Optional[str] = None
    elevation: Optional[int] = None
    height: Optional[int] = None
    width: Optional[int] = None
    file_size: Optional[int] = None
    filename: str  # required – unique per image
    camera_name: Optional[str] = None
    exposure_time: Optional[float] = None
    focal_length: Optional[float] = None
    fnumber: Optional[float] = None
    iso_speed: Optional[int] = None
    date_time: Optional[datetime] = None

    # -- Geometry --
    geometry: Optional[PointGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[ImageLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /images)
# ---------------------------------------------------------------------------

CreateImageSchema = ImageDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /images/{id})
# ---------------------------------------------------------------------------


class UpdateImageSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: ImageDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Batch create (POST /images/list)
# ---------------------------------------------------------------------------


class CreateImageListSchema(BaseModel):
    images: Optional[List[ImageDocumentSchema]] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /images/{id})
# ---------------------------------------------------------------------------


class ImageLocaleReadSchema(DocumentLocaleReadSchema):
    """Image locale as returned in GET responses."""

    title: Optional[str] = ''


class ImageReadSchema(DocumentReadSchema):
    """Full image document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``Image`` instance.
    """

    activities: Optional[List[Activities]] = None
    categories: Optional[List[ImageCategories]] = None
    image_type: Optional[ImageTypes] = None
    author: Optional[str] = None  # type: ignore[assignment]
    elevation: Optional[int] = None
    height: Optional[int] = None
    width: Optional[int] = None
    file_size: Optional[int] = None
    filename: Optional[str] = None
    camera_name: Optional[str] = None
    exposure_time: Optional[float] = None
    focal_length: Optional[float] = None
    fnumber: Optional[float] = None
    iso_speed: Optional[int] = None
    date_time: Optional[datetime] = None

    geometry: Optional[PointGeometryReadSchema] = None
    locales: Optional[List[ImageLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
