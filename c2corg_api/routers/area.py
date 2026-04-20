"""
FastAPI Area router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for areas.

During the transition both this router **and** the legacy
``c2corg_api.views.area.AreaRest`` coexist.  The FastAPI
routes are served under ``/v2/areas`` so that the legacy
``/areas`` Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE, ArchiveArea, Area
from c2corg_api.models.area import attributes as area_attributes
from c2corg_api.models.area_association import update_area
from c2corg_api.models.cache_version import update_cache_version_for_area
from c2corg_api.models.document import UpdateType
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import area_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.area import AreaReadSchema, CreateAreaSchema, UpdateAreaSchema
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/areas', tags=['areas'])

REQUIRED_FIELDS = [
    'locales',
    'locales.title',
    'geometry',
    'geometry.geom_detail',
    'area_type',
]


def _insert_associations(area, user_id):
    """Create links between a new area and existing documents."""
    update_area(area, reset=False)


def _update_associations(area, update_types):
    """Update area ↔ document links when geometry has changed."""
    if update_types:
        update_cache_version_for_area(area)
    if UpdateType.GEOM in update_types:
        update_area(area, reset=True)


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/areas
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_areas(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of areas."""
    return get_document_collection(
        area_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/areas/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_area(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single area."""
    return get_single_document(
        Area,
        document_id,
        document_type=AREA_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=AreaReadSchema,
        include_areas=False,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/areas  (moderator only)
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_area(
    body: CreateAreaSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new area document.  Requires moderator permission."""
    if not user.moderator:
        raise HTTPException(status_code=403, detail='Only moderators can create areas')

    return create_document(
        model_class=Area,
        body_schema=body,
        document_type=AREA_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        after_add=_insert_associations,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/areas/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_area_endpoint(
    document_id: DocumentId,
    body: UpdateAreaSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing area.

    Non-moderators may not change the geometry.
    """
    if not user.moderator:
        doc = body.document
        if doc and doc.geometry is not None:
            raise HTTPException(
                status_code=400, detail='No permission to change the geometry'
            )

    return update_document(
        document_id=document_id,
        model_class=Area,
        body_schema=body,
        document_type=AREA_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=area_attributes,
        user=user,
        db=db,
        after_update_types=_update_associations,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/areas/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_area_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Area, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/areas/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_area_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of an area document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=AREA_TYPE,
        archive_model=ArchiveArea,
        read_schema=AreaReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
