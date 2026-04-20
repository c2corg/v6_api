"""
FastAPI Document-Merge router.

Provides ``/v2/documents/merge`` — merge a document into another.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import (
    update_cache_version_direct,
    update_cache_version_full,
)
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.routers.helpers.document_crud import update_version
from c2corg_api.routers.helpers.linked_attributes import update_linked_route_titles
from c2corg_api.search.notify_sync import notify_es_syncer_immediate
from c2corg_api.security.fastapi_security import require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['document-merge'])

_queue_config = None


def configure_merge_router(queue_config):
    global _queue_config
    _queue_config = queue_config


class MergeSchema(BaseModel):
    source_document_id: int
    target_document_id: int


def _validate_documents(db, source_id, target_id):
    """Validate merge preconditions."""
    if source_id == target_id:
        raise HTTPException(
            status_code=400,
            detail={
                'errors': [
                    {
                        'name': 'target_document_id',
                        'description': 'Cannot merge document with itself',
                        'location': 'body',
                    }
                ]
            },
        )

    source_info = (
        db.query(Document.redirects_to, Document.type)
        .filter(Document.document_id == source_id)
        .first()
    )

    target_info = (
        db.query(Document.redirects_to, Document.type)
        .filter(Document.document_id == target_id)
        .first()
    )

    errors = []
    if not source_info:
        errors.append(
            {
                'name': 'source_document_id',
                'description': 'document {0} does not exist'.format(source_id),
                'location': 'body',
            }
        )
    if not target_info:
        errors.append(
            {
                'name': 'target_document_id',
                'description': 'document {0} does not exist'.format(target_id),
                'location': 'body',
            }
        )
    if errors:
        raise HTTPException(status_code=400, detail={'errors': errors})

    source_redirects_to, source_type = source_info
    target_redirects_to, target_type = target_info

    errors = []
    if source_redirects_to:
        errors.append(
            {
                'name': 'source_document_id',
                'description': 'document {0} is already redirected'.format(source_id),
                'location': 'body',
            }
        )
    if target_redirects_to:
        errors.append(
            {
                'name': 'target_document_id',
                'description': 'document {0} is also redirected'.format(target_id),
                'location': 'body',
            }
        )
    if errors:
        raise HTTPException(status_code=400, detail={'errors': errors})

    if source_type != target_type:
        errors.append(
            {
                'name': 'types',
                'description': 'documents must have the same type',
                'location': 'body',
            }
        )
    if source_type == USERPROFILE_TYPE:
        errors.append(
            {
                'name': 'types',
                'description': 'merging user accounts is not supported',
                'location': 'body',
            }
        )
    if errors:
        raise HTTPException(status_code=400, detail={'errors': errors})


def _delete_image_files(db, source_id):
    """Delete all image files for a merged image document.

    Schedules the deletion to happen after the current transaction
    commits successfully.
    """
    import requests as http_requests

    from c2corg_api.models.image import ArchiveImage
    from c2corg_api.routers.helpers.document_crud import _load_settings_once

    filenames_result = (
        db.query(ArchiveImage.filename)
        .filter(ArchiveImage.document_id == source_id)
        .group_by(ArchiveImage.filename)
        .all()
    )
    filenames = [f for (f,) in filenames_result]
    if not filenames:
        return

    settings = _load_settings_once()
    url = '{}/{}'.format(settings.get('image_backend.url', ''), 'delete')
    secret = settings.get('image_backend.secret_key', '')

    resp = http_requests.post(url, data={'secret': secret, 'filenames': filenames})
    if resp.status_code != 200:
        log.warning(
            'Deleting image files for document %s failed: %s %s',
            source_id,
            resp.status_code,
            resp.reason,
        )


@router.post('/documents/merge')
def merge_documents(
    body: MergeSchema,
    user: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    """Merge a document into another."""
    source_id = body.source_document_id
    target_id = body.target_document_id

    _validate_documents(db, source_id, target_id)

    source_doc = db.get(Document, source_id)
    assert source_doc is not None

    # transfer associations
    _transfer_associations(db, source_id, target_id)

    # transfer tags
    _transfer_tags(db, source_id, target_id)

    # if waypoint, update main waypoint of routes
    if source_doc.type == WAYPOINT_TYPE:
        _transfer_main_waypoint(db, source_id, target_id)

    # set redirection and create a new version
    source_doc.redirects_to = target_id
    db.flush()
    update_version(
        source_doc,
        user.id,
        'merged with {}'.format(target_id),
        [UpdateType.FIGURES],
        [],
        db=db,
    )

    # update cache versions
    update_cache_version_direct(source_id, db=db)
    update_cache_version_full(target_id, source_doc.type, db=db)

    _remove_feed_entry(db, source_id)

    if source_doc.type == IMAGE_TYPE:
        _delete_image_files(db, source_id)

    if _queue_config:
        notify_es_syncer_immediate(_queue_config)

    return {}


# ── Association transfer ────────────────────────────────────────


def _transfer_associations(db, source_id, target_id):
    target_child_ids = [
        cid
        for (cid,) in db.query(Association.child_document_id)
        .filter(Association.parent_document_id == target_id)
        .all()
    ]
    target_parent_ids = [
        pid
        for (pid,) in db.query(Association.parent_document_id)
        .filter(Association.child_document_id == target_id)
        .all()
    ]

    db.execute(
        Association.__table__.update()
        .where(
            _and_in(
                Association.parent_document_id == source_id,
                Association.child_document_id,
                target_child_ids,
            )
        )
        .values(parent_document_id=target_id)
    )
    db.execute(
        Association.__table__.update()
        .where(
            _and_in(
                Association.child_document_id == source_id,
                Association.parent_document_id,
                target_parent_ids,
            )
        )
        .values(child_document_id=target_id)
    )

    db.execute(
        Association.__table__.delete().where(
            or_(
                Association.child_document_id == source_id,
                Association.parent_document_id == source_id,
            )
        )
    )

    # transfer log entries
    db.execute(
        AssociationLog.__table__.update()
        .where(
            _and_in(
                AssociationLog.parent_document_id == source_id,
                AssociationLog.child_document_id,
                target_child_ids,
            )
        )
        .values(parent_document_id=target_id, written_at=func.now())
    )
    db.execute(
        AssociationLog.__table__.update()
        .where(
            _and_in(
                AssociationLog.child_document_id == source_id,
                AssociationLog.parent_document_id,
                target_parent_ids,
            )
        )
        .values(child_document_id=target_id, written_at=func.now())
    )

    db.execute(
        AssociationLog.__table__.delete().where(
            or_(
                AssociationLog.child_document_id == source_id,
                AssociationLog.parent_document_id == source_id,
            )
        )
    )


def _transfer_tags(db, source_id, target_id):
    target_user_ids = [
        uid
        for (uid,) in db.query(DocumentTag.user_id)
        .filter(DocumentTag.document_id == target_id)
        .all()
    ]

    db.execute(
        DocumentTag.__table__.update()
        .where(
            _and_in(
                DocumentTag.document_id == source_id,
                DocumentTag.user_id,
                target_user_ids,
            )
        )
        .values(document_id=target_id)
    )
    db.execute(
        DocumentTag.__table__.delete().where(DocumentTag.document_id == source_id)
    )

    db.execute(
        DocumentTagLog.__table__.update()
        .where(
            _and_in(
                DocumentTagLog.document_id == source_id,
                DocumentTagLog.user_id,
                target_user_ids,
            )
        )
        .values(document_id=target_id, written_at=func.now())
    )
    db.execute(
        DocumentTagLog.__table__.delete().where(DocumentTagLog.document_id == source_id)
    )


def _and_in(condition1, field2, in_ids):
    if not in_ids:
        return condition1
    else:
        return and_(condition1, not_(field2.in_(in_ids)))


def _transfer_main_waypoint(db, source_id, target_id):
    target_waypoint = db.get(Waypoint, target_id)

    db.execute(
        Route.__table__.update()
        .where(Route.main_waypoint_id == source_id)
        .values(main_waypoint_id=target_id)
    )
    update_linked_route_titles(target_waypoint, [UpdateType.LANG], None)


def _remove_feed_entry(db, source_id):
    db.query(DocumentChange).filter(DocumentChange.document_id == source_id).delete()
