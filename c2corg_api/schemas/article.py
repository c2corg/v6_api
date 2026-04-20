"""
Pydantic schemas for the Article document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import (
    Activities,
    ArticleCategories,
    ArticleTypes,
    QualityTypes,
)
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
)


class ArticleDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full article document schema for create and update requests.

    Fields mirror the SA model ``_ArticleMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Article-specific fields --
    categories: Optional[List[ArticleCategories]] = None
    activities: Optional[List[Activities]] = None
    article_type: Optional[ArticleTypes] = None

    # -- Nested objects --
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /articles)
# ---------------------------------------------------------------------------

CreateArticleSchema = ArticleDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /articles/{id})
# ---------------------------------------------------------------------------


class UpdateArticleSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: ArticleDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /articles/{id})
# ---------------------------------------------------------------------------


class ArticleReadSchema(DocumentReadSchema):
    """Full article document schema for GET responses.

    Articles have no geometry. ``from_attributes = True`` (inherited from
    ``DocumentReadSchema``) allows Pydantic to read directly from a
    SQLAlchemy ``Article`` instance.
    """

    categories: Optional[List[ArticleCategories]] = None
    activities: Optional[List[Activities]] = None
    article_type: Optional[ArticleTypes] = None

    locales: Optional[List[DocumentLocaleReadSchema]] = None

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
