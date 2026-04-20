"""
FastAPI Image router.

Handles GET (single + collection), POST, PUT, version retrieval
and document info for images.

During the transition both this router **and** the legacy
``c2corg_api.views.image.ImageRest`` coexist.  The FastAPI
routes are served under ``/v2/images`` so that the legacy
``/images`` Cornice routes remain untouched.
"""

import logging
import os
from typing import List, Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.feed import update_feed_images_upload
from c2corg_api.models.image import IMAGE_TYPE, ArchiveImage, Image
from c2corg_api.models.image import attributes as image_attributes
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_collection import get_document_collection
from c2corg_api.routers.helpers.document_crud import create_document, update_document
from c2corg_api.routers.helpers.document_get import get_single_document
from c2corg_api.routers.helpers.document_helpers import (
    set_creator as set_creator_on_documents,
)
from c2corg_api.routers.helpers.document_info import get_document_info
from c2corg_api.routers.helpers.document_schemas import image_documents_config
from c2corg_api.routers.helpers.document_version import get_document_version
from c2corg_api.routers.helpers.validation import (
    CollectionParams,
    DocumentId,
    Language,
    SingleDocParams,
    VersionId,
)
from c2corg_api.schemas.image import (
    CreateImageSchema,
    ImageReadSchema,
    UpdateImageSchema,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/images', tags=['images'])

REQUIRED_FIELDS = ['locales', 'image_type']


# ── helpers ──────────────────────────────────────────────────────────


def _set_creator(image):
    """Set the creator (first version author) on the image document."""
    set_creator_on_documents([image], 'creator')


def _check_filename_unique(
    filename: str, db: Session, exclude_document_id: int | None = None
):
    """Raise 400 if *filename* is already used by another image."""
    q = db.query(Image).filter(Image.filename == filename)
    if exclude_document_id is not None:
        q = q.filter(Image.document_id != exclude_document_id)
    if q.count() > 0:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {'name': 'filename', 'description': 'Unique', 'location': 'body'}
                ],
            },
        )


def _publish_image_in_backend(filename: str):
    """Notify the image backend that a file should be published.

    Uses the settings lazily loaded from the .ini file.
    """
    from c2corg_api.routers.helpers.document_crud import _load_settings_once

    settings = _load_settings_once()
    url = '{}/{}'.format(settings.get('image_backend.url', ''), 'publish')
    secret = settings.get('image_backend.secret_key', '')

    resp = http_requests.post(url, data={'secret': secret, 'filename': filename})
    if resp.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail='Image backend returns : {} {}'.format(
                resp.status_code, resp.reason
            ),
        )


def _check_image_update_permission(
    user: User, image: Image, new_image_type: str | None
):
    """Enforce image-type-specific update permissions.

    Mirrors the Pyramid ``ImageRest.put`` permission logic:
    - moderators may do anything
    - non-moderators may not set image_type to ``copyright``
    - collaborative images may not have their type changed by non-mods
    - personal images may only be edited by their creator
    """
    if user.moderator:
        return  # moderators bypass all checks

    if new_image_type == 'copyright' and new_image_type != image.image_type:
        raise HTTPException(
            status_code=403, detail='No permission to change to copyright type'
        )

    if image.image_type == 'collaborative':
        if new_image_type and new_image_type != image.image_type:
            raise HTTPException(
                status_code=400,
                detail='Image type cannot be changed for collaborative images',
            )
    elif image.image_type == 'personal':
        if not has_been_created_by(image.document_id, user.id):
            raise HTTPException(
                status_code=403, detail='No permission to change this image'
            )


# ──────────────────────────────────────────────────────────────
# GET collection  — /v2/images
# ──────────────────────────────────────────────────────────────


@router.get('')
def get_images(request: Request, q: CollectionParams = Depends()):
    """Return a paginated list of images."""
    return get_document_collection(
        image_documents_config,
        offset=q.offset,
        limit=q.limit,
        preferred_lang=q.pl,
        db=q.db,
        request=request,
    )


# ──────────────────────────────────────────────────────────────
# GET single  — /v2/images/{id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}')
def get_image(
    document_id: DocumentId,
    request: Request,
    response: Response,
    q: SingleDocParams = Depends(),
):
    """Return a single image document."""
    return get_single_document(
        Image,
        document_id,
        document_type=IMAGE_TYPE,
        lang=q.lang,
        editing_view=q.editing_view,
        cook=q.cook,
        read_schema=ImageReadSchema,
        include_areas=True,
        set_custom_fields=_set_creator,
        request=request,
        response=response,
        db=q.db,
    )


# ──────────────────────────────────────────────────────────────
# POST  — /v2/images
# ──────────────────────────────────────────────────────────────


@router.post('', status_code=200)
def create_image(
    body: CreateImageSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new image document."""
    # Filename uniqueness
    _check_filename_unique(body.filename, db)

    result = create_document(
        model_class=Image,
        body_schema=body,
        document_type=IMAGE_TYPE,
        required_fields=REQUIRED_FIELDS,
        user=user,
        db=db,
    )

    # Publish image to backend
    _publish_image_in_backend(body.filename)

    return result


# ──────────────────────────────────────────────────────────────
# PUT  — /v2/images/{id}
# ──────────────────────────────────────────────────────────────


@router.put('/{document_id}', status_code=200)
def update_image(
    document_id: DocumentId,
    body: UpdateImageSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing image document.

    Permission rules:
    - Moderators may do anything
    - Non-moderators may not change collaborative image types
    - Non-moderators may not set image_type to copyright
    - Personal images may only be edited by their creator
    """
    image = db.query(Image).filter(Image.document_id == document_id).first()
    if image is None:
        raise HTTPException(
            status_code=404,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'name': 'Not Found',
                        'description': 'document not found',
                        'location': 'url',
                    }
                ],
            },
        )

    new_image_type = body.document.image_type
    _check_image_update_permission(user, image, new_image_type)

    # Filename uniqueness (if changed)
    new_filename = body.document.filename
    if new_filename and new_filename != image.filename:
        _check_filename_unique(new_filename, db, exclude_document_id=document_id)

    old_filename = image.filename

    def _before_update(document, doc_schema):
        """Publish new filename to image backend if it changed."""
        if new_filename and new_filename != old_filename:
            _publish_image_in_backend(new_filename)

    return update_document(
        document_id=document_id,
        model_class=Image,
        body_schema=body,
        document_type=IMAGE_TYPE,
        required_fields=REQUIRED_FIELDS,
        type_specific_attributes=image_attributes,
        user=user,
        db=db,
        before_update=_before_update,
    )


# ──────────────────────────────────────────────────────────────
# GET info — /v2/images/{id}/{lang}/info
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/info')
def get_image_info(
    document_id: DocumentId,
    lang: Language,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return basic document info (id + best-locale title)."""
    return get_document_info(
        Image, document_id, lang, request=request, response=response, db=db
    )


# ──────────────────────────────────────────────────────────────
# GET version — /v2/images/{id}/{lang}/{version_id}
# ──────────────────────────────────────────────────────────────


@router.get('/{document_id}/{lang}/{version_id}')
def get_image_version(
    document_id: DocumentId,
    lang: Language,
    version_id: VersionId,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Return a specific version of an image document."""
    return get_document_version(
        document_id,
        lang,
        version_id,
        document_type=IMAGE_TYPE,
        archive_model=ArchiveImage,
        read_schema=ImageReadSchema,
        request=request,
        response=response,
        db=db,
        current_user=current_user,
    )


# ──────────────────────────────────────────────────────────────
# GET proxy  — /v2/images/proxy/{id}
#
# Redirects to the appropriate image URL on the image CDN,
# optionally resizing or converting the format.
# Mirrors ``ImageProxyRest.get`` from the Pyramid views.
# ──────────────────────────────────────────────────────────────

_VALID_SIZES = frozenset({'SI', 'MI', 'BI'})
_VALID_EXTENSIONS = frozenset({'webp', 'avif'})


@router.get('/proxy/{document_id}')
def get_image_proxy(
    document_id: DocumentId,
    size: Optional[str] = None,
    extension: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Redirect to the resized/converted URL for an image on the CDN.

    ``size`` must be one of ``SI``, ``MI``, ``BI`` (or absent).
    ``extension`` must be ``webp`` or ``avif`` and requires ``size``.
    """
    # Validate size
    if size is not None and size not in _VALID_SIZES:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'size',
                        'description': 'invalid size',
                        'location': 'querystring',
                    }
                ]
            },
        )

    # Validate extension
    if extension is not None:
        if extension not in _VALID_EXTENSIONS or size is None:
            raise HTTPException(
                status_code=400,
                detail={
                    'errors': [
                        {
                            'name': 'extension',
                            'description': 'invalid extension',
                            'location': 'querystring',
                        }
                    ]
                },
            )

    row = db.query(Image.filename).filter(Image.document_id == document_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail='image not found')

    filename = row.filename

    from c2corg_api.routers.helpers.document_crud import _load_settings_once

    settings = _load_settings_once()
    image_url = settings.get('image_url', '')

    if size is None:
        url = '{}{}'.format(image_url, filename)
    else:
        base, ext = os.path.splitext(filename)
        if extension is None:
            # SVG files are served as JPEG at any non-original size
            ext = '.jpg' if ext == '.svg' else ext
        else:
            ext = '.' + extension
        url = '{}{}{}{}'.format(image_url, base, size, ext)

    return RedirectResponse(url=url, status_code=302)


# ──────────────────────────────────────────────────────────────
# POST list  — /v2/images/list
#
# Bulk image creation endpoint.
# Mirrors ``ImageListRest.collection_post`` from the Pyramid views.
# ──────────────────────────────────────────────────────────────


class _ImageListBody(BaseModel):
    images: List[CreateImageSchema]


@router.post('/list', status_code=200)
def create_image_list(
    body: _ImageListBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create multiple image documents in a single request.

    Each image in the list is processed identically to a single
    ``POST /v2/images`` request.  After all images are saved, the
    feed is updated for the linked document (waypoint, outing, …).
    """
    images_in = body.images
    if not images_in:
        raise HTTPException(status_code=400, detail='images list is empty')

    created_images = []
    image_ids = []

    for img_schema in images_in:
        _check_filename_unique(img_schema.filename, db)

        result = create_document(
            model_class=Image,
            body_schema=img_schema,
            document_type=IMAGE_TYPE,
            required_fields=REQUIRED_FIELDS,
            user=user,
            db=db,
        )
        _publish_image_in_backend(img_schema.filename)

        doc = db.get(Image, result['document_id'])
        created_images.append(doc)
        image_ids.append({'document_id': result['document_id']})

    # Build the plain-dict representation expected by update_feed_images_upload
    images_in_dicts = [img.model_dump(exclude_none=True) for img in images_in]
    update_feed_images_upload(created_images, images_in_dicts, user.id)
    db.flush()

    return {'images': image_ids}
