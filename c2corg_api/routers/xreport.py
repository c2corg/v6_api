"""
FastAPI Xreport (incident/accident report) router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for xreports.

During the transition both this router **and** the legacy
``c2corg_api.views.xreport.XreportRest`` coexist.  The FastAPI
routes are served under ``/v2/xreports`` so that the legacy
``/xreports`` Cornice routes remain untouched.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.user import User
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    ArchiveXreport,
    Xreport,
    XreportLocale,
)
from c2corg_api.models.xreport import attributes as xreport_attributes
from c2corg_api.models.xreport import attributes_locales as xreport_attributes_locales
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_helpers import (
    set_creator as set_creator_on_documents,
)
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import xreport_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
    is_associated_user,
)
from c2corg_api.schemas.xreport import (
    CreateXreportSchema,
    UpdateXreportSchema,
    XreportReadSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/xreports', tags=['xreports'])

REQUIRED_FIELDS = ['locales', 'locales.title', 'geometry.geom']

# Personal fields hidden from non-authorized users
_PERSONAL_FIELDS = [
    'author_status',
    'activity_rate',
    'age',
    'gender',
    'previous_injuries',
    'autonomy',
    'supervision',
    'qualification',
]


def _set_author(xreport):
    """Set the creator (first version) as author."""
    set_creator_on_documents([xreport], 'author')


def _has_permission(user, xreport_id, db):
    """Check whether *user* may see personal fields / edit
    the xreport.  Mirrors the Pyramid ``_has_permission``.
    """
    if user is None:
        return False
    if user.moderator:
        return True
    if has_been_created_by(xreport_id, user.id, db=db):
        return True
    if is_associated_user(xreport_id, user.id, db=db):
        return True
    return False


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/xreports
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_xreports(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of xreports."""
    return get_document_collection(
        xreport_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/xreports/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_xreport(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
    user: User | None = Depends(get_optional_current_user),
):
    """Return a single xreport.

    Personal fields (``age``, ``gender``, …) are stripped for
    non-authorized users (same behaviour as the Pyramid view).
    """
    result = get_single_document(
        Xreport,
        document_id,
        document_type=XREPORT_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=XreportReadSchema,
        include_areas=True,
        set_custom_fields=_set_author,
        request=request,
        response=response,
        db=q.db,
    )

    # Strip personal data for non-authorized users
    if not _has_permission(user, document_id, q.db):
        for field in _PERSONAL_FIELDS:
            result.pop(field, None)

    return result


# ──────────────────────────────────────────────────────────────
# POST  — /v2/xreports
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_xreport(
    body: CreateXreportSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new xreport document."""
    return create_document(
        model_class=Xreport,
        body_schema=body,
        document_type=XREPORT_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
        locale_class=XreportLocale,
        allow_anonymous=True,
    )


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/xreports/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_xreport(
    document_id: DocumentId,
    body: UpdateXreportSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing xreport.

    Only moderators, the creator, and associated users may
    edit an xreport.
    """
    if not _has_permission(user, document_id, db):
        raise HTTPException(
            status_code=403,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'name': 'Forbidden',
                        'description': 'No permission to change this xreport',
                        'location': 'body',
                    }
                ],
            },
        )

    return update_document(
        document_id=document_id,
        model_class=Xreport,
        body_schema=body,
        document_type=XREPORT_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=xreport_attributes,
        user=user,
        db=db,
        locale_class=XreportLocale,
        locale_attributes=xreport_attributes_locales,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/xreports/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_xreport_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Xreport, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/xreports/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_xreport_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of an xreport document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=XREPORT_TYPE,
        archive_model=ArchiveXreport,
        read_schema=XreportReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )
