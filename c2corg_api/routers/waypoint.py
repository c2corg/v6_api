"""
FastAPI Waypoint router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for waypoints.

During the transition both this router **and** the legacy
``c2corg_api.views.waypoint.WaypointRest`` coexist.  The FastAPI
routes are served under ``/v2/waypoints`` so that the legacy
``/waypoints`` Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE,
    ArchiveWaypoint,
    Waypoint,
    WaypointLocale,
)
from c2corg_api.models.waypoint import attributes as waypoint_attributes
from c2corg_api.models.waypoint import attributes_locales as waypoint_attributes_locales
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import waypoint_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.linked_attributes import update_linked_routes
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.waypoint import (
    CreateWaypointSchema,
    UpdateWaypointSchema,
    WaypointReadSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/waypoints', tags=['waypoints'])

REQUIRED_FIELDS = ['locales', 'locales.title', 'geometry', 'geometry.geom', 'elevation']


# ──────────────────────────────────────────────────────────────
# After-update callback
# ──────────────────────────────────────────────────────────────


def _after_update(waypoint, update_types):
    """Propagate locale changes to linked routes (title_prefix)
    and recalculate public-transportation ratings.

    Wraps ``update_linked_routes(waypoint, update_types, user_id)``
    from ``views.waypoint``.  The ``user_id`` parameter is not used
    by the underlying logic, so we pass ``None``.
    """
    update_linked_routes(waypoint, update_types, user_id=None)


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/waypoints
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_waypoints(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of waypoints."""
    return get_document_collection(
        waypoint_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/waypoints/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_waypoint(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single waypoint."""
    return get_single_document(
        Waypoint,
        document_id,
        document_type=WAYPOINT_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=WaypointReadSchema,
        include_areas=True,
        include_maps=True,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/waypoints
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_waypoint(
    body: CreateWaypointSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new waypoint document."""
    return create_document(
        model_class=Waypoint,
        body_schema=body,
        document_type=WAYPOINT_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        locale_class=WaypointLocale,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/waypoints/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_waypoint(
    document_id: DocumentId,
    body: UpdateWaypointSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing waypoint."""
    return update_document(
        document_id=document_id,
        model_class=Waypoint,
        body_schema=body,
        document_type=WAYPOINT_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=waypoint_attributes,
        user=user,
        db=db,
        locale_class=WaypointLocale,
        locale_attributes=waypoint_attributes_locales,
        after_update_types=_after_update,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/waypoints/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_waypoint_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Waypoint, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/waypoints/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_waypoint_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of a waypoint document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=WAYPOINT_TYPE,
        archive_model=ArchiveWaypoint,
        read_schema=WaypointReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
