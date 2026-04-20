"""
FastAPI Coverage (Navitia coverage) router.

Handles GET (single + collection), POST and PUT for coverages.

During the transition both this router **and** the legacy
``c2corg_api.views.coverage.CoverageRest`` coexist.  The FastAPI
routes are served under ``/v2/coverages`` so that the legacy
``/coverages`` Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.coverage import COVERAGE_TYPE, Coverage
from c2corg_api.models.coverage import attributes as coverage_attributes
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_schemas import coverage_documents_config
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    SingleDocParams,
)
from c2corg_api.schemas.coverage import (
    CoverageReadSchema,
    CreateCoverageSchema,
    UpdateCoverageSchema,
)
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/coverages', tags=['coverages'])

REQUIRED_FIELDS = ['coverage_type', 'geometry', 'geometry.geom_detail']


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/coverages
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_coverages(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of coverages."""
    return get_document_collection(
        coverage_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/coverages/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_coverage(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single coverage document."""
    return get_single_document(
        Coverage,
        document_id,
        document_type=COVERAGE_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=CoverageReadSchema,
        include_areas=False,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/coverages
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_coverage(
    body: CreateCoverageSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new coverage document."""
    return create_document(
        model_class=Coverage,
        body_schema=body,
        document_type=COVERAGE_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/coverages/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_coverage(
    document_id: DocumentId,
    body: UpdateCoverageSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing coverage document."""
    return update_document(
        document_id=document_id,
        model_class=Coverage,
        body_schema=body,
        document_type=COVERAGE_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=coverage_attributes,
        user=user,
        db=db,
    )
