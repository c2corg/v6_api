"""
FastAPI TopoMap router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for topo maps.

During the transition both this router **and** the legacy
``c2corg_api.views.topo_map.TopoMapRest`` coexist.  The FastAPI
routes are served under ``/v2/maps`` so that the legacy
``/maps`` Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.cache_version import update_cache_version_for_map
from c2corg_api.models.document import UpdateType
from c2corg_api.models.topo_map import MAP_TYPE, ArchiveTopoMap, TopoMap
from c2corg_api.models.topo_map import attributes as map_attributes
from c2corg_api.models.topo_map_association import update_map
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import topo_map_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.topo_map import (
    CreateTopoMapSchema,
    TopoMapReadSchema,
    UpdateTopoMapSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/maps', tags=['maps'])

REQUIRED_FIELDS = ['locales', 'locales.title', 'geometry', 'geometry.geom_detail']


# ──────────────────────────────────────────────────────────────
# After-add / after-update callbacks
# ──────────────────────────────────────────────────────────────


def _insert_associations(topo_map, user_id):
    """Create links between this new map and documents."""
    update_map(topo_map, reset=False)


def _update_associations(topo_map, update_types):
    """Update map ↔ document links when geometry has changed."""
    if update_types:
        update_cache_version_for_map(topo_map)
    if UpdateType.GEOM in update_types:
        update_map(topo_map, reset=True)


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/maps
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_maps(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of topo maps."""
    return get_document_collection(
        topo_map_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/maps/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_map(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single topo map."""
    return get_single_document(
        TopoMap,
        document_id,
        document_type=MAP_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=TopoMapReadSchema,
        include_areas=False,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/maps  (moderator only)
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_map(
    body: CreateTopoMapSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new topo map document.  Requires moderator permission."""
    if not user.moderator:
        raise HTTPException(status_code=403, detail='Only moderators can create maps')

    return create_document(
        model_class=TopoMap,
        body_schema=body,
        document_type=MAP_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        after_add=_insert_associations,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/maps/{id}  (moderator only)
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_map_endpoint(
    document_id: DocumentId,
    body: UpdateTopoMapSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing topo map.  Requires moderator permission."""
    if not user.moderator:
        raise HTTPException(status_code=403, detail='Only moderators can update maps')

    return update_document(
        document_id=document_id,
        model_class=TopoMap,
        body_schema=body,
        document_type=MAP_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=map_attributes,
        user=user,
        db=db,
        after_update_types=_update_associations,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/maps/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_map_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        TopoMap, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/maps/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_map_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of a topo map document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=MAP_TYPE,
        archive_model=ArchiveTopoMap,
        read_schema=TopoMapReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
