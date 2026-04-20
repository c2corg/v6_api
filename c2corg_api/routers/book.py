"""
FastAPI Book router.

This is the first document type migrated from the Pyramid/Cornice stack
to FastAPI.  It handles GET (single + collection), POST, PUT, version
retrieval and document info for books.

During the transition both this router **and** the legacy
``c2corg_api.views.book.BookRest`` coexist.  The FastAPI routes are served
under ``/v2/books`` so that the legacy ``/books`` Cornice routes remain
untouched.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.book import BOOK_TYPE, ArchiveBook, Book
from c2corg_api.models.book import attributes as book_attributes
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import book_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.book import BookReadSchema, CreateBookSchema, UpdateBookSchema
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/books', tags=['books'])

# The fields required on create/update for books
REQUIRED_FIELDS = ['locales', 'locales.title', 'book_types']


# ──────────────────────────────────────────────────────────────────────
# GET collection  — /v2/books
# ──────────────────────────────────────────────────────────────────────


@router.get('')
def get_books(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of books (same contract as ``/books``)."""
    return get_document_collection(
        book_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────────────
# GET single  — /v2/books/{id}
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_book(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single book.

    Pydantic's ``BookReadSchema`` with ``from_attributes=True`` handles
    serialization directly from the SQLAlchemy ``Book`` instance — no
    intermediate ``dictify`` / ``to_json_dict`` step.
    """
    return get_single_document(
        Book,
        document_id,
        document_type=BOOK_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=BookReadSchema,
        include_areas=False,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────────────
# POST  — /v2/books
# ──────────────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_book(
    body: CreateBookSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new book document.

    Full pipeline: validation → build SA instance → persist → archive →
    areas → maps → associations → feed → ES sync.
    """
    return create_document(
        model_class=Book,
        body_schema=body,
        document_type=BOOK_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
    )


# ──────────────────────────────────────────────────────────────────────
# PUT  — /v2/books/{id}
# ──────────────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_book(
    document_id: DocumentId,
    body: UpdateBookSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing book."""
    return update_document(
        document_id=document_id,
        model_class=Book,
        body_schema=body,
        document_type=BOOK_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=book_attributes,
        user=user,
        db=db,
    )


# ──────────────────────────────────────────────────────────────────────
# GET info — /v2/books/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_book_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Book, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────────────
# GET version — /v2/books/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_book_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of a book document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=BOOK_TYPE,
        archive_model=ArchiveBook,
        read_schema=BookReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
