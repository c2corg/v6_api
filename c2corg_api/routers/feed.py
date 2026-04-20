"""
FastAPI Feed router.

Provides:
  - ``/v2/feed``           — public homepage feed
  - ``/v2/personal-feed``  — personal feed for authenticated user
  - ``/v2/profile-feed``   — profile feed for a given user

Mirrors ``c2corg_api.views.feed``.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.routers.helpers.feed import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    get_changes_of_feed,
    get_changes_of_personal_feed,
    get_changes_of_profile_feed,
    load_feed,
)
from c2corg_api.security.fastapi_security import (
    get_current_user,
    get_optional_current_user,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['feed'])

# Module-level cache — set once by ``configure_feed_router``.
_feed_admin_user_account_id: int | None = None


def configure_feed_router(settings: dict) -> None:
    """Called once at startup to capture the feed admin user setting."""
    global _feed_admin_user_account_id
    raw = settings.get('feed.admin_user_account')
    _feed_admin_user_account_id = int(raw) if raw else None


def _get_feed_admin_filter():
    """Build an ignore-admin-entries filter, or None."""
    from c2corg_api.models.feed import DocumentChange

    if _feed_admin_user_account_id is None:
        return None
    return DocumentChange.user_id != _feed_admin_user_account_id


def _parse_pagination(token: Optional[str], limit: Optional[int]):
    """Parse and validate pagination params, returning
    (token_id, token_time, effective_limit).
    """
    import urllib.parse

    from dateutil import parser as datetime_parser

    token_id = None
    token_time = None
    if token is not None:
        if ',' in token:
            parts = token.split(',', 1)
            try:
                token_id = int(parts[0])
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail={
                        'status': 'error',
                        'errors': [
                            {
                                'location': 'querystring',
                                'name': 'token',
                                'description': 'invalid format',
                            }
                        ],
                    },
                )
            try:
                raw_time = urllib.parse.unquote(parts[1])
                token_time = datetime_parser.parse(raw_time)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail={
                        'status': 'error',
                        'errors': [
                            {
                                'location': 'querystring',
                                'name': 'token',
                                'description': 'invalid format',
                            }
                        ],
                    },
                )
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'location': 'querystring',
                            'name': 'token',
                            'description': 'invalid format',
                        }
                    ],
                },
            )

    effective_limit = min(
        DEFAULT_PAGE_LIMIT if limit is None else limit, MAX_PAGE_LIMIT
    )
    return token_id, token_time, effective_limit


# ──────────────────────────────────────────────────────────────
# GET /v2/feed — public feed
# ──────────────────────────────────────────────────────────────


@router.get('/feed')
def get_feed(
    pl: Optional[str] = Query(None, description='Preferred language'),
    token: Optional[str] = Query(None, description='Pagination token'),
    limit: Optional[int] = Query(None, description='Max entries'),
    db: Session = Depends(get_db),
):
    """Return the public homepage feed."""
    token_id, token_time, effective_limit = _parse_pagination(token, limit)
    ignore_admin_filter = _get_feed_admin_filter()
    changes = get_changes_of_feed(
        token_id, token_time, effective_limit, ignore_admin_filter
    )
    return load_feed(changes, pl)


# ──────────────────────────────────────────────────────────────
# GET /v2/personal-feed — authenticated personal feed
# ──────────────────────────────────────────────────────────────


@router.get('/personal-feed')
def get_personal_feed(
    pl: Optional[str] = Query(None, description='Preferred language'),
    token: Optional[str] = Query(None, description='Pagination token'),
    limit: Optional[int] = Query(None, description='Max entries'),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the personal feed for the authenticated user."""
    token_id, token_time, effective_limit = _parse_pagination(token, limit)
    ignore_admin_filter = _get_feed_admin_filter()
    changes = get_changes_of_personal_feed(
        user.id, token_id, token_time, effective_limit, ignore_admin_filter
    )
    return load_feed(changes, pl)


# ──────────────────────────────────────────────────────────────
# GET /v2/profile-feed — profile feed for a given user
# ──────────────────────────────────────────────────────────────


@router.get('/profile-feed')
def get_profile_feed(
    u: str = Query(..., description='User id'),
    pl: Optional[str] = Query(None, description='Preferred language'),
    token: Optional[str] = Query(None, description='Pagination token'),
    limit: Optional[int] = Query(None, description='Max entries'),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Return the profile feed for a given user."""
    from sqlalchemy.orm import load_only as sa_load_only

    # Validate user id
    try:
        user_id = int(u)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {'location': 'querystring', 'name': 'u', 'description': 'invalid u'}
                ],
            },
        )

    token_id, token_time, effective_limit = _parse_pagination(token, limit)

    # Load the requested user
    requested_user = (
        resolve_db(None)
        .query(User)
        .filter(User.id == user_id)
        .filter(User.email_validated)
        .options(sa_load_only(User.id, User.is_profile_public))
        .first()
    )

    if not requested_user:
        raise HTTPException(status_code=404, detail='user not found')

    if requested_user.is_profile_public or current_user is not None:
        changes = get_changes_of_profile_feed(
            user_id, token_id, token_time, effective_limit
        )
        return load_feed(changes, pl)
    else:
        raise HTTPException(status_code=403, detail='no permission to see the feed')
