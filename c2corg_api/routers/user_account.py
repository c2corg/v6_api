"""
FastAPI User Account router.

Provides:
  - ``GET  /v2/users/account``                    — read account info
  - ``POST /v2/users/account``                    — update account
  - ``POST /v2/users/update_preferred_language``  — change language

Mirrors ``c2corg_api.views.user_account``.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.emails.email_service import get_email_service_from_settings
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.user import Purpose, User
from c2corg_api.routers.helpers.user import (
    VALIDATION_EXPIRE_DAYS,
    check_forum_username,
    is_unused_user_attribute,
)
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/users', tags=['user-account'])

# Module-level settings — set once by ``configure_user_account_router``.
_settings: dict = {}


def configure_user_account_router(settings: dict) -> None:
    global _settings
    _settings = settings


# ──────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────


class UpdatePreferredLangBody(BaseModel):
    lang: DefaultLangs


class UpdateAccountBody(BaseModel):
    currentpassword: str
    email: Optional[str] = None
    name: Optional[str] = None
    forum_username: Optional[str] = None
    newpassword: Optional[str] = None
    is_profile_public: Optional[bool] = None


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


class _ErrorCollector:
    def __init__(self):
        self.errors: list[dict] = []

    def add(self, location, name, description):
        self.errors.append(
            {'location': location, 'name': name, 'description': description}
        )

    def __bool__(self):
        return bool(self.errors)


def _raise_errors(errors: _ErrorCollector):
    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors.errors}
        )


def _validate_account_fields(body: UpdateAccountBody, errors, db):
    if body.currentpassword and len(body.currentpassword) < 3:
        errors.add('body', 'currentpassword', 'Shorter than minimum length 3')

    if body.email is not None:
        if '@' not in body.email:
            errors.add('body', 'email', 'Invalid email')
        elif not is_unused_user_attribute('email', body.email, db=db):
            errors.add('body', 'email', 'Already used email')

    if body.name is not None and len(body.name) < 3:
        errors.add('body', 'name', 'Shorter than minimum length 3')

    if body.forum_username is not None:
        if not is_unused_user_attribute(
            'forum_username', body.forum_username, lowercase=True, db=db
        ):
            errors.add('body', 'forum_username', 'Already used forum name')

    if body.newpassword is not None and len(body.newpassword) < 3:
        errors.add('body', 'newpassword', 'Shorter than minimum length 3')


def _validate_forum_username(body, errors):
    if body.forum_username is not None:
        res = check_forum_username(body.forum_username)
        if res is not False:
            errors.add('body', 'forum_username', res)


# ──────────────────────────────────────────────────────────────
# GET /v2/users/account
# ──────────────────────────────────────────────────────────────


@router.get('/account')
def get_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    loaded_user = db.get(User, user.id)
    return {
        'email': loaded_user.email,
        'name': loaded_user.name,
        'forum_username': loaded_user.forum_username,
        'is_profile_public': loaded_user.is_profile_public,
    }


# ──────────────────────────────────────────────────────────────
# POST /v2/users/account
# ──────────────────────────────────────────────────────────────


@router.post('/account')
def update_account(
    body: UpdateAccountBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    errors = _ErrorCollector()
    _validate_account_fields(body, errors, db)
    _validate_forum_username(body, errors)
    _raise_errors(errors)

    loaded_user = db.get(User, user.id)

    # Check current password
    if not loaded_user.validate_password(body.currentpassword):
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'currentpassword',
                        'description': 'Invalid password',
                    }
                ],
            },
        )

    result = {}
    sync_sso = False

    if body.newpassword is not None:
        loaded_user.password = body.newpassword

    email_link = None
    if body.email is not None and body.email != loaded_user.email:
        loaded_user.email_to_validate = body.email
        loaded_user.update_validation_nonce(
            Purpose.change_email, VALIDATION_EXPIRE_DAYS
        )
        nonce = loaded_user.validation_nonce
        link = _settings['mail.validate_change_email_url_template'].format('#', nonce)
        email_link = link
        result['email'] = body.email
        result['sent_email'] = True
        sync_sso = True

    update_search_index = False
    if body.name is not None:
        loaded_user.name = body.name
        result['name'] = loaded_user.name
        update_search_index = True
        sync_sso = True

    if body.forum_username is not None:
        loaded_user.forum_username = body.forum_username
        result['forum_username'] = loaded_user.forum_username
        update_search_index = True
        sync_sso = True

    if body.is_profile_public is not None:
        loaded_user.is_profile_public = body.is_profile_public

    if sync_sso:
        try:
            client = get_discourse_client(_settings)
            client.sync_sso(loaded_user)
        except Exception:
            log.error('Error syncing with discourse', exc_info=True)
            raise HTTPException(status_code=500, detail='Error with Discourse')

    try:
        db.flush()
    except Exception:
        log.warning('Error persisting user', exc_info=True)
        raise HTTPException(status_code=500, detail='Error persisting user')

    if email_link:
        email_service = get_email_service_from_settings(_settings)
        email_service.send_change_email_confirmation(loaded_user, email_link)

    if update_search_index:
        try:
            from c2corg_api.search import get_queue_config

            queue_config = get_queue_config(_settings)
            notify_es_syncer(queue_config)
        except Exception:
            log.warning('Could not notify ES syncer', exc_info=True)
        update_cache_version(loaded_user.profile)

    return result


# ──────────────────────────────────────────────────────────────
# POST /v2/users/update_preferred_language
# ──────────────────────────────────────────────────────────────


@router.post('/update_preferred_language')
def update_preferred_language(
    body: UpdatePreferredLangBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loaded_user = db.get(User, user.id)
    loaded_user.lang = body.lang
    db.flush()
    return {}
