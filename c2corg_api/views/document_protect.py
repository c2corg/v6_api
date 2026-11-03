import logging

from c2corg_api import DBSession
from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int
from c2corg_api.views.document import DocumentRest
from c2corg_api.views.resource import write

log = logging.getLogger(__name__)


class ProtectSchema(Schema):
    document_id: Int


def _get_document(document_id):
    document = DBSession.get(Document, document_id)

    if not document:
        raise HTTPBadRequest(f'Unknown document {document_id}')

    return document


@write(validators=[body_validator(ProtectSchema)], permission='moderator', json=True)
def protect_document(request):
    """Mark the given document as not editable.

    Request:
        `POST` `/documents/protect`

    Request body:
        {'document_id': @document_id@}

    """
    document_id = request.validated['document_id']
    document = _get_document(document_id)

    # Do nothing if document is already protected.
    if document.protected:
        return {}

    document.protected = True

    user_id = request.authenticated_userid
    DocumentRest.update_version(
        document, user_id, 'Protected document', [UpdateType.FIGURES], []
    )

    update_cache_version_direct(document_id)

    return {}


@write(validators=[body_validator(ProtectSchema)], permission='moderator', json=True)
def unprotect_document(request):
    """Mark the given document as editable.

    Request:
        `POST` `/documents/unprotect`

    Request body:
        {'document_id': @document_id@}

    """
    document_id = request.validated['document_id']
    document = _get_document(document_id)

    # Do nothing if document is already not protected.
    if not document.protected:
        return {}

    document.protected = False

    user_id = request.authenticated_userid
    DocumentRest.update_version(
        document, user_id, 'Unprotected document', [UpdateType.FIGURES], []
    )

    update_cache_version_direct(document_id)

    return {}
