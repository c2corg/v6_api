"""
FastAPI Document-Changes router.

Provides ``/v2/documents/changes`` — the public document changes feed.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload, load_only

from c2corg_api.database import get_db
from c2corg_api.models.document import ArchiveDocumentLocale, Document
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-changes'])

DEFAULT_LIMIT = 30
MAX_LIMIT = 50


@router.get('/documents/changes')
def get_document_changes(
    token: Optional[str] = Query(None, description='Pagination token'),
    limit: Optional[int] = Query(None, description='Max results'),
    u: Optional[str] = Query(None, description='Filter by user id'),
    db: Session = Depends(get_db),
):
    """Get the public document changes feed."""
    # Validate token
    token_id = None
    if token is not None:
        try:
            token_id = int(token)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail={
                    'errors': [
                        {
                            'name': 'token',
                            'description': 'invalid format',
                            'location': 'querystring',
                        }
                    ]
                },
            )

    # Validate user_id
    user_id = None
    if u is not None:
        try:
            user_id = int(u)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail={
                    'errors': [
                        {
                            'name': 'u',
                            'description': 'invalid u',
                            'location': 'querystring',
                        }
                    ]
                },
            )

    # Compute limit
    if limit is None:
        limit = DEFAULT_LIMIT
    limit = min(limit, MAX_LIMIT)

    # Get changes
    changes = _get_changes_of_feed(db, token_id, limit, user_id)
    doc_ids = [change.history_metadata_id for change in changes]

    return _load_feed(db, doc_ids, limit, user_id)


def _get_changes_of_feed(db, token_id, limit, user_id=None):
    query = (
        db.query(DocumentVersion.history_metadata_id)
        .join(HistoryMetaData)
        .join(Document)
        .filter(Document.type.notin_([OUTING_TYPE, USERPROFILE_TYPE]))
        .order_by(desc(DocumentVersion.history_metadata_id))
    )

    if token_id is not None:
        query = query.filter(DocumentVersion.history_metadata_id < token_id)

    if user_id is not None:
        query = query.filter(HistoryMetaData.user_id == user_id)

    return query.limit(limit).all()


def _load_feed(db, doc_ids, limit, user_id=None):
    if not doc_ids:
        doc_changes = []
    else:
        doc_changes = (
            db.query(DocumentVersion)
            .options(
                load_only(DocumentVersion.lang),
                joinedload(DocumentVersion.history_metadata)
                .load_only(
                    HistoryMetaData.id,
                    HistoryMetaData.user_id,
                    HistoryMetaData.comment,
                    HistoryMetaData.written_at,
                )
                .joinedload(HistoryMetaData.user)
                .load_only(User.id, User.name, User.username, User.lang),
            )
            .options(
                joinedload(DocumentVersion.document).load_only(
                    Document.version,
                    Document.document_id,
                    Document.type,
                    Document.quality,
                )
            )
            .options(
                joinedload(DocumentVersion.document_locales_archive).load_only(
                    ArchiveDocumentLocale.title
                )
            )
            .order_by(desc(DocumentVersion.id))
            .filter(DocumentVersion.history_metadata_id.in_(doc_ids))
            .limit(limit)
            .all()
        )

    if not doc_changes:
        return {'feed': []}

    last_change = doc_changes[-1]
    pagination_token = '{}'.format(last_change.history_metadata_id)

    return {
        'pagination_token': pagination_token,
        'feed': [_serialize_change(ch) for ch in doc_changes],
    }


def _serialize_change(change):
    return {
        'written_at': change.history_metadata.written_at.isoformat(),
        'lang': change.lang,
        'document': {
            'version': change.document.version,
            'document_id': change.document.document_id,
            'title': change.document_locales_archive.title,
            'type': change.document.type,
            'quality': change.document.quality,
        },
        'user': {
            'user_id': change.history_metadata.user_id,
            'name': change.history_metadata.user.name,
            'username': change.history_metadata.user.username,
            'lang': change.history_metadata.user.lang,
        },
        'version_id': change.id,
        'comment': change.history_metadata.comment,
    }
