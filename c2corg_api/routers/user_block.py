"""
FastAPI User Block router.

Provides:
  - ``POST /v2/users/block``           — block a user
  - ``POST /v2/users/unblock``         — unblock a user
  - ``GET  /v2/users/blocked/{id}``    — check if a user is blocked
  - ``GET  /v2/users/blocked``         — list all blocked users

Mirrors ``c2corg_api.views.user_block``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_listings import get_documents_for_ids
from c2corg_api.routers.helpers.document_schemas import user_profile_documents_config
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.fastapi_security import require_moderator

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/users', tags=['user-block'])

# Module-level settings — set by ``configure_user_block_router``.
_settings: dict = {}


def configure_user_block_router(settings: dict) -> None:
    global _settings
    _settings = settings


# ── Pydantic schemas ─────────────────────────────────────────


class BlockBody(BaseModel):
    user_id: int


# ── Helpers ──────────────────────────────────────────────────


def _get_user(user_id: int, db: Session):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'user_id',
                        'description': ('Unknown user {}'.format(user_id)),
                    }
                ],
            },
        )
    return user


def _validate_user_id(user_id: int, db: Session):
    """Check that the user exists (for body user_id)."""
    exists = db.query(User).filter(User.id == user_id).first()
    if not exists:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'user_id',
                        'description': ('user {} does not exist'.format(user_id)),
                    }
                ],
            },
        )


# ── POST /v2/users/block ────────────────────────────────────


@router.post('/block')
def block_user(
    body: BlockBody,
    mod: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    _validate_user_id(body.user_id, db)
    user = _get_user(body.user_id, db)

    try:
        client = get_discourse_client(_settings)
        block_duration = 99999
        client.suspend(user.id, block_duration, 'account blocked by moderator')
    except Exception:
        log.error('Suspending account in Discourse failed: %d', user.id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'Internal Server Error',
                        'description': ('Suspending account in Discourse failed'),
                    }
                ],
            },
        )

    user.blocked = True
    return {}


# ── POST /v2/users/unblock ──────────────────────────────────


@router.post('/unblock')
def unblock_user(
    body: BlockBody,
    mod: User = Depends(require_moderator),
    db: Session = Depends(get_db),
):
    _validate_user_id(body.user_id, db)
    user = _get_user(body.user_id, db)

    try:
        client = get_discourse_client(_settings)
        client.unsuspend(user.id)
    except Exception:
        log.error(
            'Unsuspending account in Discourse failed: %d', user.id, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'Internal Server Error',
                        'description': ('Unsuspending account in Discourse failed'),
                    }
                ],
            },
        )

    user.blocked = False
    user.ratelimit_times = 0
    return {}


# ── GET /v2/users/blocked/{id} ──────────────────────────────


@router.get('/blocked/{user_id}')
def get_blocked_status(
    user_id: int, mod: User = Depends(require_moderator), db: Session = Depends(get_db)
):
    if user_id < 0:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'querystring',
                        'name': 'id',
                        'description': 'invalid id',
                    }
                ],
            },
        )

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'querystring',
                        'name': 'id',
                        'description': ('Unknown user {}'.format(user_id)),
                    }
                ],
            },
        )

    return {'blocked': user.blocked}


# ── GET /v2/users/blocked ───────────────────────────────────


@router.get('/blocked')
def get_all_blocked(
    mod: User = Depends(require_moderator), db: Session = Depends(get_db)
):
    blocked_user_ids = db.query(User.id).filter(User.blocked).all()
    blocked_user_ids = [uid for (uid,) in blocked_user_ids]

    blocked_users = get_documents_for_ids(
        blocked_user_ids, None, user_profile_documents_config
    ).get('documents')

    return {'blocked': blocked_users}
