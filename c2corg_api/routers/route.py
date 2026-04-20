"""
FastAPI Route router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for routes.

During the transition both this router **and** the legacy
``c2corg_api.views.route.RouteRest`` coexist.  The FastAPI
routes are served under ``/v2/routes`` so that the legacy
``/routes`` Cornice routes remain untouched.
"""

import functools
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.route import ROUTE_TYPE, ArchiveRoute, Route, RouteLocale
from c2corg_api.models.route import attributes as route_attributes
from c2corg_api.models.route import attributes_locales as route_attributes_locales
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import route_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.linked_attributes import (
    init_linked_attributes,
    set_default_geometry,
    set_recent_outings,
    update_all_pt_rating,
    update_default_geometry,
    update_linked_attributes,
)
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.route import (
    CreateRouteSchema,
    RouteReadSchema,
    UpdateRouteSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
    require_moderator,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/routes', tags=['routes'])

REQUIRED_FIELDS = ['locales', 'locales.title', 'geometry.geom', 'activities']


def _set_recent_outings(route, lang):
    """Set last 10 outings on the given route."""
    set_recent_outings(route, lang)


def _validate_main_waypoint(document_dict):
    """Check that main_waypoint_id (if set) has a matching waypoint
    association.  Mirrors the Pyramid ``validate_main_waypoint``.
    """
    main_waypoint_id = document_dict.get('main_waypoint_id')
    if not main_waypoint_id:
        return

    associations = document_dict.get('associations')
    if associations:
        linked_waypoints = associations.get('waypoints', [])
        for linked_wp in linked_waypoints:
            wp_id = (
                linked_wp.get('document_id')
                if isinstance(linked_wp, dict)
                else getattr(linked_wp, 'document_id', None)
            )
            if wp_id == main_waypoint_id:
                return

    raise HTTPException(
        status_code=400,
        detail={
            'status': 'error',
            'errors': [
                {
                    'name': 'Bad Request',
                    'description': 'no association to the main waypoint',
                    'location': 'body',
                }
            ],
        },
    )


def _validate_required_waypoint_associations(document_dict):
    """Ensure at least one waypoint association is present.
    Mirrors the Pyramid ``validate_required_associations``.
    """
    associations = document_dict.get('associations')
    if associations:
        linked_waypoints = associations.get('waypoints', [])
        if linked_waypoints:
            return

    raise HTTPException(
        status_code=400,
        detail={
            'status': 'error',
            'errors': [
                {
                    'name': 'Bad Request',
                    'description': 'at least one waypoint required',
                    'location': 'body',
                }
            ],
        },
    )


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/routes
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_routes(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of routes."""
    return get_document_collection(
        route_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET  — /v2/routes/update_public_transportation_rating
# ──────────────────────────────────────────────────────────────


@router.get('/update_public_transportation_rating')
def update_public_transportation_rating(
    waypoint_extrapolation: bool = True, user: User = Depends(require_moderator)
):
    """Update the public transportation rating of every route
    based on linked waypoints.

    Requires moderator permission.

    Parameters
    ----------
    waypoint_extrapolation
        Whether to extrapolate starting and ending points
        (default ``True``).
    """
    update_all_pt_rating(waypoint_extrapolation)
    return {}


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/routes/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_route(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single route.

    Includes recent outings via ``set_custom_associations``.
    """
    return get_single_document(
        Route,
        document_id,
        document_type=ROUTE_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=RouteReadSchema,
        include_areas=True,
        set_custom_associations=_set_recent_outings,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/routes
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_route(
    body: CreateRouteSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new route document.

    Validates required waypoint associations and main waypoint
    consistency before creating.
    """
    document_dict = body.model_dump(exclude_none=False)

    # Route-specific validations
    _validate_required_waypoint_associations(document_dict)
    _validate_main_waypoint(document_dict)

    # Extract linked waypoints for default geometry computation
    linked_waypoints = (
        document_dict.get('associations', {}).get('waypoints', [])
        if document_dict.get('associations')
        else []
    )

    return create_document(
        model_class=Route,
        body_schema=body,
        document_type=ROUTE_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        locale_class=RouteLocale,
        before_add=functools.partial(set_default_geometry, linked_waypoints),
        after_add=init_linked_attributes,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/routes/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_route(
    document_id: DocumentId,
    body: UpdateRouteSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing route document.

    Validates required waypoint associations and main waypoint
    consistency before updating.
    """
    doc_dict = body.document.model_dump(exclude_none=False)

    # Route-specific validations (on update, associations may be absent
    # if the user is only changing document fields)
    associations = doc_dict.get('associations')
    if associations:
        _validate_required_waypoint_associations(doc_dict)
        _validate_main_waypoint(doc_dict)

    def _before_update(document, doc_schema):
        update_default_geometry(document, doc_schema)

    def _after_update(document, doc_schema):
        update_linked_attributes(document, None, None)

    return update_document(
        document_id=document_id,
        model_class=Route,
        body_schema=body,
        document_type=ROUTE_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=route_attributes,
        user=user,
        db=db,
        locale_class=RouteLocale,
        locale_attributes=route_attributes_locales,
        before_update=_before_update,
        after_update=_after_update,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/routes/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_route_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Route, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/routes/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_route_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of a route document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=ROUTE_TYPE,
        archive_model=ArchiveRoute,
        read_schema=RouteReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
