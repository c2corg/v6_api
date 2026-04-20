"""
FastAPI User Follow router.

Provides:
  - ``POST /v2/users/follow``              — follow a user
  - ``POST /v2/users/unfollow``            — unfollow a user
  - ``GET  /v2/users/following-user/{id}`` — check if following
  - ``GET  /v2/users/following``           — list followed users

Mirrors ``c2corg_api.views.user_follow``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_listings import get_documents_for_ids
from c2corg_api.routers.helpers.document_schemas import user_profile_documents_config
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/users', tags=['user-follow'])


# ── Pydantic schemas ─────────────────────────────────────────


class FollowBody(BaseModel):
    user_id: int


# ── Helpers ──────────────────────────────────────────────────


def _get_follower_relation(followed_user_id: int, follower_user_id: int, db: Session):
    return (
        db.query(FollowedUser)
        .filter(FollowedUser.followed_user_id == followed_user_id)
        .filter(FollowedUser.follower_user_id == follower_user_id)
        .first()
    )


def _validate_user_id(user_id: int, db: Session):
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


# ── POST /v2/users/follow ───────────────────────────────────


@router.post('/follow')
def follow_user(
    body: FollowBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_user_id(body.user_id, db)
    followed_user_id = body.user_id
    follower_user_id = user.id

    relation = _get_follower_relation(followed_user_id, follower_user_id, db)
    if not relation:
        db.add(
            FollowedUser(
                followed_user_id=followed_user_id, follower_user_id=follower_user_id
            )
        )

    return {}


# ── POST /v2/users/unfollow ─────────────────────────────────


@router.post('/unfollow')
def unfollow_user(
    body: FollowBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_user_id(body.user_id, db)
    followed_user_id = body.user_id
    follower_user_id = user.id

    relation = _get_follower_relation(followed_user_id, follower_user_id, db)
    if relation:
        db.delete(relation)
    else:
        log.warning(
            'tried to delete not existing follower relation (%s, %s)',
            followed_user_id,
            follower_user_id,
        )

    return {}


# ── GET /v2/users/following-user/{id} ───────────────────────


@router.get('/following-user/{user_id}')
def is_following_user(
    user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
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

    relation = _get_follower_relation(user_id, user.id, db)
    return {'is_following': relation is not None}


# ── GET /v2/users/following ─────────────────────────────────


@router.get('/following')
def get_following(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    followed_user_ids = (
        db.query(FollowedUser.followed_user_id)
        .filter(FollowedUser.follower_user_id == user.id)
        .all()
    )
    followed_user_ids = [uid for (uid,) in followed_user_ids]

    followed_users = get_documents_for_ids(
        followed_user_ids, None, user_profile_documents_config
    ).get('documents')

    return {'following': followed_users}
