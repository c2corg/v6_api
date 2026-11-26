"""Turn an image already published: a new file, a new version of the image."""

# The image service turns the file and makes its thumbnails under a new
# filename, which a new version of the image keeps (the old versions keep the
# old one). A moderator can turn any image; its author, a personal image only:
# a collaborative image is turned by mistake more often than not.

import os
from typing import Literal

import requests

from c2corg_api.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPInternalServerError,
)
from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.document import UpdateType
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.image import Image
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document import update_version
from c2corg_api.views.image import image_backend_endpoint
from c2corg_api.views.resource import write


class RotateSchema(Schema):
    document_id: Int
    # degrees, clockwise
    rotation: Literal[90, -90, 180] = 90


def _image(request):
    document_id = request.validated['document_id']
    image = DBSession.get(Image, document_id)
    if image is None or image.redirects_to:
        raise HTTPBadRequest(f'Unknown image {document_id}')
    if not request.has_permission('moderator') and not (
        image.image_type == 'personal'
        and has_been_created_by(document_id, request.authenticated_userid)
    ):
        raise HTTPForbidden('No permission to rotate this image')
    if os.path.splitext(image.filename)[1].lower() == '.svg':
        raise HTTPBadRequest('An SVG image cannot be rotated')
    return image


def rotate_image_file(request, filename, rotation):
    """Turn an image file on the image service; return the new filename."""
    settings = request.registry.settings
    response = requests.post(
        image_backend_endpoint(settings, 'rotate'),
        data={
            'secret': settings['image_backend.secret_key'],
            'filename': filename,
            'rotation': str(rotation),
        },
        timeout=int(settings['url.timeout']),
    )
    if response.status_code != 200:
        raise HTTPInternalServerError(
            f'Rotating the image failed: {response.status_code} {response.reason}'
        )
    return response.json()['filename']


@write(
    validators=[body_validator(RotateSchema)],
    permission='authenticated',
    json=True,
)
def rotate_image(request):
    """Turn an image by a quarter or a half turn."""
    # `POST` `/images/rotate`
    # {'document_id': @document_id@, 'rotation': 90 | -90 | 180}
    image = _image(request)
    image.filename = rotate_image_file(
        request, image.filename, request.validated['rotation']
    )
    update_version(
        image, request.authenticated_userid, 'Rotated image', [UpdateType.FIGURES], []
    )
    # the documents that show the image too
    update_cache_version(image)
    notify_es_syncer(request.registry.queue_config)
    return {'filename': image.filename}
