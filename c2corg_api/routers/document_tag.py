"""
FastAPI Document-Tag router.

Provides ``/v2/tags/add``, ``/v2/tags/remove``, ``/v2/tags/has/{document_id}``
— manage "todo" tags on route documents.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.document import Document
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.search.notify_sync import notify_es_syncer_immediate
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-tag'])

# Module-level cache — set once by ``configure_tag_router``.
_queue_config = None


def configure_tag_router(queue_config):
    global _queue_config
    _queue_config = queue_config


class DocumentTagSchema(BaseModel):
    document_id: int


def _get_tag_relation(db: Session, user_id: int, document_id: int):
    return (
        db.query(DocumentTag)
        .filter(DocumentTag.user_id == user_id)
        .filter(DocumentTag.document_id == document_id)
        .first()
    )


def _validate_document(db: Session, document_id: int):
    """Check that the document exists, is a route and not merged."""
    document_exists = db.query(
        db.query(Document)
        .filter(Document.document_id == document_id)
        .filter(Document.type == ROUTE_TYPE)
        .filter(Document.redirects_to.is_(None))
        .exists()
    ).scalar()
    if not document_exists:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'document_id',
                        'description': 'document {0} does not exist'.format(
                            document_id
                        ),
                        'location': 'body',
                    }
                ]
            },
        )


@router.post('/tags/add')
def add_tag(
    body: DocumentTagSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tag the given document as todo."""
    _validate_document(db, body.document_id)

    if _get_tag_relation(db, user.id, body.document_id):
        raise HTTPException(status_code=400, detail='This document is already tagged.')

    db.add(
        DocumentTag(
            user_id=user.id, document_id=body.document_id, document_type=ROUTE_TYPE
        )
    )
    db.add(
        DocumentTagLog(
            user_id=user.id,
            document_id=body.document_id,
            document_type=ROUTE_TYPE,
            is_creation=True,
        )
    )

    if _queue_config:
        notify_es_syncer_immediate(_queue_config)

    return {}


@router.post('/tags/remove')
def remove_tag(
    body: DocumentTagSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Untag the given document."""
    _validate_document(db, body.document_id)

    tag_relation = _get_tag_relation(db, user.id, body.document_id)

    if not tag_relation:
        raise HTTPException(status_code=400, detail='This document has no such tag.')

    db.delete(tag_relation)
    db.add(
        DocumentTagLog(
            user_id=user.id,
            document_id=body.document_id,
            document_type=ROUTE_TYPE,
            is_creation=False,
        )
    )

    if _queue_config:
        notify_es_syncer_immediate(_queue_config)

    return {}


@router.get('/tags/has/{document_id}')
def has_tag(
    document_id: int = Path(..., ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if the authenticated user has tagged the given document."""
    tag_relation = _get_tag_relation(db, user.id, document_id)
    return {'todo': tag_relation is not None}
