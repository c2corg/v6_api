"""
Pydantic schemas for the UserProfile document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from c2corg_api.models.common.attributes import Activities, QualityTypes, UserCategories
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
    PointGeometryReadSchema,
    PointGeometrySchema,
)


class UserProfileLocaleSchema(DocumentLocaleSchema):
    """Locale for user-profile updates.

    User profiles do not have a meaningful title — the field is accepted
    on input but silently reset to ``''`` by the view.
    """

    title: Optional[str] = None


class UserProfileDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full user-profile document schema for update requests.

    Fields mirror the SA model ``_UserProfileMixin`` + ``Document`` base
    columns that are relevant for the API contract.
    """

    # -- Document base fields (optional) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- UserProfile-specific fields --
    activities: Optional[List[Activities]] = None
    categories: Optional[List[UserCategories]] = None

    # -- Geometry --
    geometry: Optional[PointGeometrySchema] = None

    # -- Nested objects --
    locales: Optional[List[UserProfileLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Update (PUT /profiles/{id})
# (user profiles are only updated, never created via API)
# ---------------------------------------------------------------------------


class UpdateUserProfileSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: UserProfileDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /profiles/{id})
# ---------------------------------------------------------------------------


class UserProfileLocaleReadSchema(DocumentLocaleReadSchema):
    """UserProfile locale as returned in GET responses.

    User profiles do not have a title.  The DB stores ``''`` but the API
    omits the key entirely (matching the Pyramid colander schema which
    listed only ``['version', 'lang', 'description', 'summary']``).
    """

    title: Optional[str] = Field(default=None, exclude=True)

    model_config = ConfigDict(from_attributes=True)


class UserProfileReadSchema(DocumentReadSchema):
    """Full user-profile document schema for GET responses.

    ``from_attributes = True`` (inherited from ``DocumentReadSchema``) allows
    Pydantic to read directly from a SQLAlchemy ``UserProfile`` instance.
    ``name`` and ``forum_username`` are exposed via association proxy on the
    SA model and are already declared on ``DocumentReadSchema``.
    """

    activities: Optional[List[Activities]] = None
    categories: Optional[List[UserCategories]] = None

    geometry: Optional[PointGeometryReadSchema] = None
    locales: Optional[List[UserProfileLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
