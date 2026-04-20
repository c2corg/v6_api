"""
FastAPI Association-History router.

Provides ``/v2/associations-history`` — returns the history of
document association changes (creation / removal).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from c2corg_api.database import get_db
from c2corg_api.models.association import AssociationLog
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['association-history'])

# max/default sizes of requests
LIMIT_MAX = 500
LIMIT_DEFAULT = 50


@router.get('/associations-history')
def get_association_history(
    d: Optional[int] = Query(None, description='Document id'),
    u: Optional[int] = Query(None, description='User id'),
    offset: int = Query(0, ge=0),
    limit: int = Query(LIMIT_DEFAULT, ge=1, le=LIMIT_MAX),
    db: Session = Depends(get_db),
):
    """Return the history of association changes.

    Parameters
    ----------
    d : int, optional
        Filter by document id (parent or child).
    u : int, optional
        Filter by the user who made the change.
    offset : int
        Pagination offset.
    limit : int
        Maximum number of results (capped at 500).
    """

    user_join = joinedload(AssociationLog.user).load_only(
        User.id,
        User.name,
        User.forum_username,
        User.robot,
        User.moderator,
        User.blocked,
    )

    child_join = (
        joinedload(AssociationLog.child_document)
        .load_only(Document.document_id, Document.type)
        .joinedload(Document.locales)
        .load_only(DocumentLocale.title, DocumentLocale.lang)
    )

    parent_join = (
        joinedload(AssociationLog.parent_document)
        .load_only(Document.document_id, Document.type)
        .joinedload(Document.locales)
        .load_only(DocumentLocale.title, DocumentLocale.lang)
    )

    query = (
        db.query(AssociationLog)
        .options(user_join)
        .options(parent_join)
        .options(child_join)
    )

    if d is not None:
        query = query.filter(
            or_(
                AssociationLog.parent_document_id == d,
                AssociationLog.child_document_id == d,
            )
        )

    if u is not None:
        query = query.filter(AssociationLog.user_id == u)

    count = query.count()

    results = query.order_by(AssociationLog.id.desc()).limit(limit).offset(offset).all()

    return {
        'count': count,
        'associations': [
            _serialize_association_log(log_entry) for log_entry in results
        ],
    }


def _serialize_document(document):
    result = {
        'document_id': document.document_id,
        'type': document.type,
        'locales': [
            {'lang': locale.lang, 'title': locale.title} for locale in document.locales
        ],
    }

    if document.type == USERPROFILE_TYPE:
        result['name'] = document.name

    return result


def _serialize_association_log(log_entry):
    return {
        'written_at': log_entry.written_at.isoformat(),
        'is_creation': log_entry.is_creation,
        'user': {
            'user_id': log_entry.user.id,
            'name': log_entry.user.name,
            'forum_username': log_entry.user.forum_username,
            'robot': log_entry.user.robot,
            'moderator': log_entry.user.moderator,
            'blocked': log_entry.user.blocked,
        },
        'child_document': _serialize_document(log_entry.child_document),
        'parent_document': _serialize_document(log_entry.parent_document),
    }
