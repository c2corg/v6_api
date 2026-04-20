"""
FastAPI Outing router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for outings.

During the transition both this router **and** the legacy
``c2corg_api.views.outing.OutingRest`` coexist.  The FastAPI
routes are served under ``/v2/outings`` so that the legacy
``/outings`` Cornice routes remain untouched.
"""

import functools
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.association import Association
from c2corg_api.models.outing import OUTING_TYPE, ArchiveOuting, Outing, OutingLocale
from c2corg_api.models.outing import attributes as outing_attributes
from c2corg_api.models.outing import attributes_locales as outing_attributes_locales
from c2corg_api.models.user import User
from c2corg_api.models.utils import get_mid_point
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import (
    create_document,
    set_default_geom_from_associations,
    update_document,
)
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import outing_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.outing import (
    CreateOutingSchema,
    OutingReadSchema,
    UpdateOutingSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/outings', tags=['outings'])

REQUIRED_FIELDS = ['locales', 'locales.title', 'activities', 'date_start', 'date_end']


# ──────────────────────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────────────────────


def _validate_dates(date_start, date_end):
    """Validate outing dates: not in the future, end >= start."""
    utc_now = datetime.now(timezone.utc)
    utc_now_plus_12h = (utc_now + timedelta(hours=12)).date()

    errors = []
    if date_start and date_start > utc_now_plus_12h:
        errors.append(
            {
                'name': 'date_start',
                'description': 'can not be sometime in the future',
                'location': 'body',
            }
        )
    if date_end and date_end > utc_now_plus_12h:
        errors.append(
            {
                'name': 'date_end',
                'description': 'can not be sometime in the future',
                'location': 'body',
            }
        )
    if not errors and date_start and date_end and date_end < date_start:
        errors.append(
            {
                'name': 'date_end',
                'description': 'can not be prior the starting date',
                'location': 'body',
            }
        )
    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors}
        )


def _validate_required_associations(document_dict):
    """Ensure at least one user and one route association."""
    errors = []
    associations = document_dict.get('associations')
    if not associations:
        errors.append(
            {
                'name': 'associations.users',
                'description': 'at least one user required',
                'location': 'body',
            }
        )
        errors.append(
            {
                'name': 'associations.routes',
                'description': 'at least one route required',
                'location': 'body',
            }
        )
    else:
        linked_users = associations.get('users', [])
        if not linked_users:
            errors.append(
                {
                    'name': 'associations.users',
                    'description': 'at least one user required',
                    'location': 'body',
                }
            )
        linked_routes = associations.get('routes', [])
        if not linked_routes:
            errors.append(
                {
                    'name': 'associations.routes',
                    'description': 'at least one route required',
                    'location': 'body',
                }
            )
    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors}
        )


def _has_permission_for_outing(user, outing_id, db):
    """Check whether the user may modify the outing.

    Moderators can edit any outing; normal users can only edit
    outings they are associated with.
    """
    if user.moderator:
        return True
    return db.query(
        exists().where(
            and_(
                Association.parent_document_id == user.id,
                Association.child_document_id == outing_id,
            )
        )
    ).scalar()


# ──────────────────────────────────────────────────────────────
# Geometry helpers (mirrored from views/outing.py)
# ──────────────────────────────────────────────────────────────


def set_default_geometry(linked_routes, outing, user_id):
    """When creating a new outing, set the default geometry to the
    middle point of a given track, or the centroid of the convex
    hull of all associated routes.
    """
    if outing.geometry is not None and outing.geometry.geom is not None:
        return

    if outing.geometry is not None and outing.geometry.geom_detail is not None:
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)
        return

    set_default_geom_from_associations(outing, linked_routes)


def update_default_geometry(outing, outing_in):
    """When updating an outing, set the default geometry to the
    middle point of a new track if provided.
    """
    geometry_in = outing_in.geometry

    if geometry_in is not None and geometry_in.geom_detail is not None:
        geometry_in.geom = get_mid_point(geometry_in.geom_detail)


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/outings
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_outings(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of outings."""
    return get_document_collection(
        outing_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/outings/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_outing(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single outing."""
    return get_single_document(
        Outing,
        document_id,
        document_type=OUTING_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=OutingReadSchema,
        include_areas=True,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/outings
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_outing(
    body: CreateOutingSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new outing document.

    Validates required associations (at least one user + one route)
    and date constraints.
    """
    document_dict = body.model_dump(exclude_none=False)

    # Outing-specific validations
    _validate_required_associations(document_dict)
    _validate_dates(body.date_start, body.date_end)

    # Extract linked routes for default geometry computation
    linked_routes = (
        document_dict.get('associations', {}).get('routes', [])
        if document_dict.get('associations')
        else []
    )

    return create_document(
        model_class=Outing,
        body_schema=body,
        document_type=OUTING_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        locale_class=OutingLocale,
        before_add=functools.partial(set_default_geometry, linked_routes),
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/outings/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_outing(
    document_id: DocumentId,
    body: UpdateOutingSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing outing.

    Only associated users (or moderators) may modify outings.
    """
    if not _has_permission_for_outing(user, document_id, db):
        raise HTTPException(
            status_code=403, detail='No permission to change this outing'
        )

    doc_dict = body.document.model_dump(exclude_none=False)

    # Validate required associations if present in the payload
    associations = doc_dict.get('associations')
    if associations:
        _validate_required_associations(doc_dict)

    # Validate dates
    _validate_dates(body.document.date_start, body.document.date_end)

    def _before_update(document, doc_schema):
        update_default_geometry(document, doc_schema)

    return update_document(
        document_id=document_id,
        model_class=Outing,
        body_schema=body,
        document_type=OUTING_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=outing_attributes,
        user=user,
        db=db,
        locale_class=OutingLocale,
        locale_attributes=outing_attributes_locales,
        before_update=_before_update,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/outings/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_outing_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Outing, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/outings/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_outing_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of an outing document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=OUTING_TYPE,
        archive_model=ArchiveOuting,
        read_schema=OutingReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
