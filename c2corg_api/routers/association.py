"""
FastAPI Association router.

Provides ``/v2/associations`` — create and delete associations
between documents.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.association import Association, SchemaAssociation, exists_already
from c2corg_api.models.cache_version import update_cache_version_associations
from c2corg_api.models.common.associations import valid_associations
from c2corg_api.models.document import Document
from c2corg_api.models.feed import update_feed_association_update
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.routers.helpers.validation import (
    ErrorCollector,
    check_permission_for_association_removal,
    validate_association_permission,
)
from c2corg_api.scripts.es import sync
from c2corg_api.search.notify_sync import notify_es_syncer_immediate
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['associations'])

# Module-level cache — set once by ``configure_association_router``.
_queue_config = None


def configure_association_router(queue_config) -> None:
    """Called once at startup to capture the queue_config."""
    global _queue_config
    _queue_config = queue_config


def _validate_association(body: SchemaAssociation, user: User, db: Session):
    """Check if the given documents exist and if an association between the
    two document types is valid.

    Returns (parent_type, child_type) on success.
    Raises HTTPException(400) on failure.
    """
    errors = ErrorCollector()
    parent_document_id = body.parent_document_id
    child_document_id = body.child_document_id

    parent_document_type = (
        db.query(Document.type)
        .filter(Document.document_id == parent_document_id)
        .filter(Document.redirects_to.is_(None))
        .scalar()
    )
    if not parent_document_type:
        errors.add(
            'body',
            'parent_document_id',
            'parent document does not exist or is redirected',
        )

    child_document_type = (
        db.query(Document.type)
        .filter(Document.document_id == child_document_id)
        .filter(Document.redirects_to.is_(None))
        .scalar()
    )
    if not child_document_type:
        errors.add(
            'body',
            'child_document_id',
            'child document does not exist or is redirected',
        )

    if parent_document_type and child_document_type:
        association_type = (parent_document_type, child_document_type)
        if association_type not in valid_associations:
            errors.add('body', 'association', 'invalid association type')
        else:
            validate_association_permission(
                user.id,
                user.moderator,
                parent_document_id,
                parent_document_type,
                child_document_id,
                child_document_type,
                errors=errors,
            )

    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors.errors}
        )

    return parent_document_type, child_document_type


@router.post('/associations', status_code=200)
def create_association(
    body: SchemaAssociation,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new association between two documents."""
    parent_document_type, child_document_type = _validate_association(body, user, db)

    association = Association(
        parent_document_id=body.parent_document_id,
        child_document_id=body.child_document_id,
    )
    association.parent_document_type = parent_document_type
    association.child_document_type = child_document_type

    if exists_already(association, db=db):
        raise HTTPException(
            status_code=400, detail='association (or its back-link) exists already'
        )

    db.add(association)
    db.add(association.get_log(user.id))

    update_cache_version_associations(
        [
            {
                'parent_id': association.parent_document_id,
                'parent_type': association.parent_document_type,
                'child_id': association.child_document_id,
                'child_type': association.child_document_type,
            }
        ],
        [],
        db=db,
    )

    _notify_es_syncer_if_needed(association)
    update_feed_association_update(
        association.parent_document_id,
        association.parent_document_type,
        association.child_document_id,
        association.child_document_type,
        user.id,
        db=db,
    )

    return {}


@router.delete('/associations', status_code=200)
def delete_association(
    body: SchemaAssociation,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an association between two documents."""
    association_in = Association(
        parent_document_id=body.parent_document_id,
        child_document_id=body.child_document_id,
    )

    association = _load_association(db, association_in)
    if association is None:
        # also accept {parent_document_id: y, child_document_id: x} when
        # for an association {parent_document_id: x, child_document_id: y}
        association_in = Association(
            parent_document_id=association_in.child_document_id,
            child_document_id=association_in.parent_document_id,
        )
        association = _load_association(db, association_in)
        if association is None:
            raise HTTPException(status_code=400, detail='association does not exist')

    _check_required_associations(association, db)

    # Permission check — raises HTTPException(400) when not permitted
    check_permission_for_association_removal(user.id, user.moderator, association)

    log_entry = association.get_log(user.id, is_creation=False)

    db.delete(association)
    db.add(log_entry)

    update_cache_version_associations(
        [],
        [
            {
                'parent_id': association.parent_document_id,
                'parent_type': association.parent_document_type,
                'child_id': association.child_document_id,
                'child_type': association.child_document_type,
            }
        ],
        db=db,
    )

    _notify_es_syncer_if_needed(association)
    update_feed_association_update(
        association.parent_document_id,
        association.parent_document_type,
        association.child_document_id,
        association.child_document_type,
        user.id,
        db=db,
    )

    return {}


def _load_association(db, association_in):
    return (
        db.query(Association)
        .filter(
            Association.parent_document_id == association_in.parent_document_id,
            Association.child_document_id == association_in.child_document_id,
        )
        .first()
    )


def _check_required_associations(association, db):
    if _is_main_waypoint_association(association, db):
        raise HTTPException(
            status_code=400,
            detail='as the main waypoint of the route, this waypoint can not be disassociated',
        )
    elif _is_last_waypoint_of_route(association, db):
        raise HTTPException(
            status_code=400,
            detail='as the last waypoint of the route, this waypoint can not be disassociated',
        )
    elif _is_last_route_of_outing(association, db):
        raise HTTPException(
            status_code=400,
            detail='as the last route of the outing, this route can not be disassociated',
        )


def _is_main_waypoint_association(association, db):
    return db.query(
        exists()
        .where(Route.document_id == association.child_document_id)
        .where(Route.main_waypoint_id == association.parent_document_id)
    ).scalar()


def _is_last_waypoint_of_route(association, db):
    if not (
        association.parent_document_type == WAYPOINT_TYPE
        and association.child_document_type == ROUTE_TYPE
    ):
        return False

    route_has_other_waypoints = (
        exists()
        .where(Association.parent_document_type == WAYPOINT_TYPE)
        .where(Association.child_document_type == ROUTE_TYPE)
        .where(Association.parent_document_id != association.parent_document_id)
        .where(Association.child_document_id == association.child_document_id)
    )

    return not db.query(route_has_other_waypoints).scalar()


def _is_last_route_of_outing(association, db):
    if not (
        association.parent_document_type == ROUTE_TYPE
        and association.child_document_type == OUTING_TYPE
    ):
        return False

    outing_has_other_routes = (
        exists()
        .where(Association.parent_document_type == ROUTE_TYPE)
        .where(Association.child_document_type == OUTING_TYPE)
        .where(Association.parent_document_id != association.parent_document_id)
        .where(Association.child_document_id == association.child_document_id)
    )

    return not db.query(outing_has_other_routes).scalar()


def _notify_es_syncer_if_needed(association):
    if sync.requires_updates(association) and _queue_config is not None:
        notify_es_syncer_immediate(_queue_config)
