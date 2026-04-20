"""
FastAPI SSO router.

Provides:
  - ``/v2/sso_sync``  — SSO sync endpoint
  - ``/v2/sso_login`` — SSO login endpoint

Mirrors ``c2corg_api.views.sso``.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.routers.helpers.sso import (
    generate_token,
    localized_now,
    sso_expire_from_now,
)
from c2corg_api.routers.helpers.user import check_forum_username
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.fastapi_security import _get_jwt_key
from c2corg_api.security.roles import AccountBlockedError, log_validated_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['sso'])

# Module-level settings cache — set once by ``configure_sso_router``.
_settings: dict = {}


def configure_sso_router(settings: dict) -> None:
    """Called once at startup to capture settings."""
    global _settings
    _settings = settings


# ──────────────────────────────────────────────────────────────
# SSO Sync
# ──────────────────────────────────────────────────────────────


class SsoSyncBody(BaseModel):
    sso_key: str
    external_id: str
    email: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None
    forum_username: Optional[str] = None
    lang: Optional[DefaultLangs] = None
    groups: Optional[str] = None


class _ErrorCollector:
    """Lightweight error collector mimicking Pyramid's request.errors."""

    def __init__(self):
        self.errors = []
        self.status = 400

    def add(self, location, name, description):
        self.errors.append(
            {'location': location, 'name': name, 'description': description}
        )


def _is_unused_user_attribute(db, attrname, value, lowercase=False):
    """Check if user attribute value is unused (using the injected session)."""
    attr = getattr(User, attrname)
    query = db.query(User)
    if lowercase:
        query = query.filter(func.lower(attr) == value.lower())
    else:
        query = query.filter(attr == value)
    return query.count() == 0


def _validate_unique_attribute(db, attrname, validated, errors, lowercase=False):
    """Validate that a user attribute value is unique."""
    value = validated.get(attrname)
    if value is not None:
        if _is_unused_user_attribute(db, attrname, value, lowercase=lowercase):
            pass  # valid
        else:
            errors.add('body', attrname, 'already used ' + attrname)


def _validate_forum_username(validated, errors):
    """Validate the forum_username field."""
    value = validated.get('forum_username')
    if value is not None:
        result = check_forum_username(value)
        if result is not False:
            errors.add('body', 'forum_username', result)


def _call_discourse(method, *args, **kwargs):
    """Call a Discourse method, raising FastAPI HTTPException on failure."""
    try:
        return method.__call__(*args, **kwargs)
    except Exception as e:
        log.error('Error with Discourse: {}'.format(str(e)), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'discourse',
                        'description': 'Error with Discourse',
                    }
                ],
            },
        )


def _get_discourse_userid(client, userid):
    """Get discourse user id with 404 handling."""
    from c2corg_api.security.discourse_client import DiscourseClientError

    try:
        return client.get_userid(userid)
    except DiscourseClientError as e:
        if e.response.status_code == 404:
            return None
        raise


@router.post('/sso_sync')
def sso_sync(body: SsoSyncBody, db: Session = Depends(get_db)):
    """Synchronize user details and return authentication URL."""
    validated = body.model_dump()
    errors = _ErrorCollector()

    # Validate sso_key
    sso_key = db.query(SsoKey).filter(SsoKey.key == validated['sso_key']).one_or_none()
    if sso_key is None:
        log.warning('Attempt to use sso_sync with bad key')
        raise HTTPException(
            status_code=403,
            detail={
                'status': 'error',
                'errors': [
                    {'location': 'body', 'name': 'sso_key', 'description': 'Invalid'}
                ],
            },
        )

    # Search user by external_id
    user = None
    sso_external_id = (
        db.query(SsoExternalId)
        .filter(SsoExternalId.domain == sso_key.domain)
        .filter(SsoExternalId.external_id == validated['external_id'])
        .one_or_none()
    )
    if sso_external_id is not None:
        user = sso_external_id.user

    if user is None:
        # Search by email
        if validated.get('email') is None:
            raise HTTPException(
                status_code=400,
                detail={
                    'status': 'error',
                    'errors': [
                        {'location': 'body', 'name': 'email', 'description': 'Required'}
                    ],
                },
            )
        user = db.query(User).filter(User.email == validated['email']).one_or_none()

    if user is None:
        # Creating new user — validate all required fields
        username = validated.get('username')
        if username is None:
            errors.add('body', 'username', 'Required')
        validated['name'] = validated.get('name') or username
        validated['forum_username'] = validated.get('forum_username') or username
        if validated.get('lang') is None:
            errors.add('body', 'lang', 'Required')

        _validate_unique_attribute(db, 'email', validated, errors)
        _validate_unique_attribute(db, 'username', validated, errors)
        _validate_forum_username(validated, errors)
        _validate_unique_attribute(
            db, 'forum_username', validated, errors, lowercase=True
        )

        if errors.errors:
            raise HTTPException(
                status_code=400, detail={'status': 'error', 'errors': errors.errors}
            )

        user = User(
            username=validated['username'],
            name=validated['name'],
            forum_username=validated['forum_username'],
            email=validated['email'],
            email_validated=True,
            lang=validated['lang'],
            password=generate_token(),
        )
        lang = user.lang
        user.profile = UserProfile(
            categories=['amateur'], locales=[DocumentLocale(lang=lang, title='')]
        )
        db.add(user)
        db.flush()

    if sso_external_id is None:
        sso_external_id = SsoExternalId(
            domain=sso_key.domain, external_id=validated['external_id'], user=user
        )
        db.add(sso_external_id)

    sso_external_id.token = generate_token()
    sso_external_id.expire = sso_expire_from_now()

    client = get_discourse_client(_settings)
    discourse_userid = _call_discourse(_get_discourse_userid, client, user.id)
    if discourse_userid is None:
        _call_discourse(client.sync_sso, user)
        discourse_userid = client.get_userid(user.id)

    # Groups
    group_ids = []
    discourse_groups = None
    groups = validated.get('groups') or ''
    for group_name in groups.split(','):
        if group_name == '':
            continue
        if discourse_groups is None:
            discourse_groups = _call_discourse(client.client.groups)

        group_id = None
        for discourse_group in discourse_groups:
            if discourse_group['name'] == group_name:
                group_id = discourse_group['id']

        if group_id is not None:
            group_ids.append(group_id)

    for group_id in group_ids:
        _call_discourse(client.client.add_user_to_group, group_id, discourse_userid)

    from urllib.parse import urlencode

    return {
        'url': '{}/sso-login?no_redirect&{}'.format(
            _settings.get('ui.url', ''), urlencode({'token': sso_external_id.token})
        )
    }


# ──────────────────────────────────────────────────────────────
# SSO Login
# ──────────────────────────────────────────────────────────────


class SsoLoginBody(BaseModel):
    token: str
    discourse: Optional[bool] = None


def _token_to_response(user, token):
    """Build the login response dict (framework-agnostic)."""
    expire_time = token.expire - datetime(1970, 1, 1, tzinfo=timezone.utc)
    roles = ['moderator'] if user.moderator else []
    return {
        'token': token.value,
        'username': user.username,
        'name': user.name,
        'forum_username': user.forum_username,
        'expire': int(expire_time.total_seconds()),
        'roles': roles,
        'id': user.id,
        'lang': user.lang,
    }


def _log_validated_user_sso(user, db):
    """FastAPI-compatible wrapper around ``roles.log_validated_user``."""
    try:
        return log_validated_user(user, jwt_key=_get_jwt_key(), session=db)
    except AccountBlockedError:
        raise HTTPException(status_code=403, detail='account blocked')


@router.post('/sso_login')
def sso_login(body: SsoLoginBody, db: Session = Depends(get_db)):
    """Authenticate via SSO token."""
    sso_external_id = (
        db.query(SsoExternalId)
        .filter(SsoExternalId.token == body.token)
        .filter(SsoExternalId.expire > localized_now())
        .one_or_none()
    )
    if sso_external_id is None:
        log.warning('Attempt to use sso_login with bad token')
        raise HTTPException(
            status_code=403,
            detail={
                'status': 'error',
                'errors': [
                    {'location': 'body', 'name': 'token', 'description': 'Invalid'}
                ],
            },
        )

    user = sso_external_id.user
    token = _log_validated_user_sso(user, db)
    response = _token_to_response(user, token)

    if body.discourse:
        client = get_discourse_client(_settings)
        try:
            r = client.redirect_without_nonce(user)
            response['redirect_internal'] = r
        except Exception:
            log.warning('Error logging into discourse for %d', user.id, exc_info=True)

    return response
