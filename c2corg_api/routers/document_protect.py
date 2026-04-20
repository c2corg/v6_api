"""
FastAPI Document-Protect router.

Provides ``/v2/documents/protect`` and ``/v2/documents/unprotect`` —
mark a document as non-editable or editable.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_crud import update_version
from c2corg_api.security.fastapi_security import require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-protect'])


class ProtectSchema(BaseModel):
    document_id: int


def _get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=400, detail='Unknown document {}'.format(document_id)
        )
    return document


@router.post('/documents/protect')
def protect_document(
    body: ProtectSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Mark the given document as not editable."""
    document = _get_document(db, body.document_id)

    # Do nothing if document is already protected.
    if document.protected:
        return {}

    document.protected = True
    db.flush()

    update_version(
        document, user.id, 'Protected document', [UpdateType.FIGURES], [], db=db
    )

    update_cache_version_direct(document.document_id)

    return {}


@router.post('/documents/unprotect')
def unprotect_document(
    body: ProtectSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Mark the given document as editable."""
    document = _get_document(db, body.document_id)

    # Do nothing if document is already not protected.
    if not document.protected:
        return {}

    document.protected = False
    db.flush()

    update_version(
        document, user.id, 'Unprotected document', [UpdateType.FIGURES], [], db=db
    )

    update_cache_version_direct(document.document_id)

    return {}
