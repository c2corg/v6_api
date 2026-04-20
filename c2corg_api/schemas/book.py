"""
Pydantic schemas for the Book document type.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from c2corg_api.models.common.attributes import Activities, BookTypes, QualityTypes
from c2corg_api.schemas import (
    AssociationsSchema,
    DocumentLocaleReadSchema,
    DocumentLocaleSchema,
    DocumentReadSchema,
    DuplicateLocalesMixin,
)


class BookDocumentSchema(DuplicateLocalesMixin, BaseModel):
    """Full book document schema for create and update requests.

    Fields mirror the SA model ``_BookMixin`` + ``Document`` base columns
    that are relevant for the API contract.
    """

    # -- Document base fields (optional on create) --
    document_id: Optional[int] = None
    version: Optional[int] = None
    quality: Optional[QualityTypes] = None

    # -- Book-specific fields --
    author: Optional[str] = None
    editor: Optional[str] = None
    activities: Optional[List[Activities]] = None
    url: Optional[str] = None
    isbn: Optional[str] = None
    book_types: Optional[List[BookTypes]] = None
    nb_pages: Optional[int] = None
    publication_date: Optional[str] = None
    langs: Optional[List[str]] = None

    # -- Nested objects --
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Create (POST /books)
# ---------------------------------------------------------------------------

CreateBookSchema = BookDocumentSchema


# ---------------------------------------------------------------------------
# Update (PUT /books/{id})
# ---------------------------------------------------------------------------


class UpdateBookSchema(BaseModel):
    """Update envelope: ``{"message": "...", "document": {...}}``."""

    message: str = ''
    document: BookDocumentSchema

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Read (GET /books/{id})
# ---------------------------------------------------------------------------


class BookReadSchema(DocumentReadSchema):
    """Full book document schema for GET responses.

    Books have no geometry. ``from_attributes = True`` (inherited from
    ``DocumentReadSchema``) allows Pydantic to read directly from a
    SQLAlchemy ``Book`` instance.
    """

    author: Optional[str] = None  # type: ignore[assignment]
    editor: Optional[str] = None
    activities: Optional[List[Activities]] = None
    url: Optional[str] = None
    isbn: Optional[str] = None
    book_types: Optional[List[BookTypes]] = None
    nb_pages: Optional[int] = None
    publication_date: Optional[str] = None
    langs: Optional[List[str]] = None

    locales: Optional[List[DocumentLocaleReadSchema]] = None
    # Books have no geometry — field intentionally absent.

    # Redirect support — only present when the document is merged.
    redirects_to: Optional[int] = None

    # Cooked markdown — only present when ``?cook=`` is used.
    cooked: Optional[dict] = None
