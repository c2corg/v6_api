"""
FastAPI User router.

Provides user registration, login, logout, renew, password change,
and email validation endpoints.

Mirrors ``c2corg_api.views.user``.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.emails.email_service import get_email_service_from_settings
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user import Purpose, User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.routers.helpers.document_crud import create_new_version
from c2corg_api.routers.helpers.user import (
    ENCODING,
    MINIMUM_PASSWORD_LENGTH,
    VALIDATION_EXPIRE_DAYS,
    check_forum_username,
    is_unused_user_attribute,
    is_valid_email,
)
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.fastapi_security import (
    _extract_token,
    _get_jwt_key,
    get_current_user,
)
from c2corg_api.security.roles import (
    AccountBlockedError,
    log_validated_user,
    remove_token,
    renew_token,
    try_login,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/users', tags=['users'])

_settings: dict = {}


def configure_user_router(settings: dict) -> None:
    global _settings
    _settings = settings


# ── Pydantic schemas ─────────────────────────────────────────


class RegisterBody(BaseModel):
    username: str
    forum_username: str
    name: str
    email: EmailStr
    password: str
    lang: Optional[DefaultLangs] = DefaultLangs.fr
    captcha: Optional[str] = None
    model_config = {'extra': 'ignore'}


class LoginBody(BaseModel):
    username: str
    password: str
    accept_tos: Optional[bool] = False
    discourse: Optional[bool] = None
    sso: Optional[str] = None
    sig: Optional[str] = None
    model_config = {'extra': 'ignore'}


class LogoutBody(BaseModel):
    discourse: Optional[bool] = None
    model_config = {'extra': 'ignore'}


class PasswordBody(BaseModel):
    password: str
    model_config = {'extra': 'ignore'}


class RequestPasswordChangeBody(BaseModel):
    email: str
    model_config = {'extra': 'ignore'}


# ── Helpers ──────────────────────────────────────────────────


class _ErrorCollector:
    def __init__(self):
        self.errors: list[dict] = []

    def add(self, location, name, description):
        self.errors.append(
            {'location': location, 'name': name, 'description': description}
        )

    def __bool__(self):
        return bool(self.errors)


def _raise_errors(ec, status_code=400):
    if ec:
        raise HTTPException(
            status_code=status_code, detail={'status': 'error', 'errors': ec.errors}
        )


def _token_to_response(user, token):
    assert token is not None
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


def _add_or_retrieve_token(value, expire, userid, db):
    """Delegates to roles.add_or_retrieve_token with explicit session."""
    from c2corg_api.security.roles import add_or_retrieve_token

    return add_or_retrieve_token(value, expire, userid, session=db)


def _log_validated_user(user, db):
    """FastAPI-compatible wrapper around ``roles.log_validated_user``."""
    try:
        return log_validated_user(user, jwt_key=_get_jwt_key(), session=db)
    except AccountBlockedError:
        raise HTTPException(status_code=403, detail='account blocked')


def _try_login(user, password, db):
    """FastAPI-compatible wrapper around ``roles.try_login``."""
    try:
        return try_login(user, password, jwt_key=_get_jwt_key(), session=db)
    except AccountBlockedError:
        raise HTTPException(status_code=403, detail='account blocked')


def _renew_token(user, request, db):
    """FastAPI-compatible wrapper around ``roles.renew_token``."""
    token_str = _extract_token(request)
    return renew_token(user, token_str, jwt_key=_get_jwt_key(), session=db)


def _validate_captcha(captcha, ec):
    skip = _settings.get('skip.captcha.validation', 'false')
    if str(skip).lower() in ('true', '1', 'yes', 'on'):
        return
    if not captcha:
        ec.add('body', 'captcha', 'Missing captcha')
        return
    timeout = int(_settings.get('url.timeout', 5))
    secret = _settings.get('recaptcha.secret.key', '')
    url = 'https://www.google.com/recaptcha/api/siteverify'
    try:
        r = http_requests.post(
            url, timeout=timeout, data={'secret': secret, 'response': captcha}
        )
        if not r.json()['success']:
            ec.add('body', 'captcha', 'Error, please retry')
    except Exception:
        log.exception('Request error while checking captcha')
        ec.add('body', 'captcha', 'Internal error, please retry')


def _validate_password(password, ec):
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        ec.add('body', 'password', 'Password too short')
        return None
    try:
        return password.encode(ENCODING)
    except Exception:
        ec.add('body', 'password', 'Invalid')
        return None


def _validate_username(username, email, ec, db):
    username = username.strip()
    if not username:
        ec.add('body', 'username', 'Username cannot be empty or whitespaces')
        return username
    if not is_unused_user_attribute('username', username, lowercase=True, db=db):
        ec.add('body', 'username', 'This username already exists')
    if is_valid_email(username) and email != username:
        ec.add(
            'body',
            'username',
            'An email address used as username should be '
            'the same as the one used as the account '
            'email address.',
        )
    return username


def _validate_forum_username_value(value, ec):
    res = check_forum_username(value)
    if res is not False:
        ec.add('body', 'forum_username', res)


def _validate_user_from_nonce(purpose, nonce, db):
    now = datetime.now(timezone.utc)
    user = (
        db.query(User)
        .filter(
            and_(User.validation_nonce == nonce, User.validation_nonce_expire > now)
        )
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'querystring',
                        'name': 'nonce',
                        'description': 'invalid nonce',
                    }
                ],
            },
        )
    if not user.validate_nonce_purpose(purpose):
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'querystring',
                        'name': 'nonce',
                        'description': 'unexpected purpose',
                    }
                ],
            },
        )
    return user


def _log_and_build_token_response(user, db):
    token = _log_validated_user(user, db)
    if token:
        return _token_to_response(user, token)
    return None


# ── POST /register ───────────────────────────────────────────


@router.post('/register')
def register(body: RegisterBody, db: Session = Depends(get_db)):
    ec = _ErrorCollector()
    encoded_pw = _validate_password(body.password, ec)

    if not is_unused_user_attribute('email', body.email, db=db):
        ec.add('body', 'email', 'already used email')

    if not is_unused_user_attribute(
        'forum_username', body.forum_username, lowercase=True
    ):
        ec.add('body', 'forum_username', 'already used forum_username')

    username = _validate_username(body.username, body.email, ec, db=db)
    _validate_forum_username_value(body.forum_username, ec)
    _validate_captcha(body.captcha, ec)
    _raise_errors(ec)

    user = User(
        username=username,
        forum_username=body.forum_username,
        name=body.name,
        email=body.email,
        lang=body.lang,
    )
    user.password = encoded_pw
    user.update_validation_nonce(Purpose.registration, VALIDATION_EXPIRE_DAYS)
    user.profile = UserProfile(
        categories=['amateur'], locales=[DocumentLocale(lang=user.lang, title='')]
    )
    user.tos_validated = datetime.now(timezone.utc)

    db.add(user)
    try:
        db.flush()
    except Exception:
        log.warning('Error persisting user', exc_info=True)
        raise HTTPException(status_code=500, detail='Error persisting user')

    create_new_version(user.profile, user.id, db=db)

    svc = get_email_service_from_settings(_settings)
    nonce = user.validation_nonce
    link = _settings['mail.validate_register_url_template'].format('#', nonce)
    svc.send_registration_confirmation(user, link)

    return {
        'id': user.id,
        'username': user.username,
        'forum_username': user.forum_username,
        'name': user.name,
        'email': user.email,
        'email_validated': user.email_validated,
        'moderator': user.moderator,
    }


# ── POST /login ──────────────────────────────────────────────


@router.post('/login')
def login(body: LoginBody, db: Session = Depends(get_db)):
    ec = _ErrorCollector()
    encoded_pw = _validate_password(body.password, ec)
    _raise_errors(ec)

    user = db.query(User).filter(User.username == body.username).first()
    if user is None and is_valid_email(body.username):
        user = db.query(User).filter(User.email == body.username).first()

    token = _try_login(user, encoded_pw, db) if user else None

    if not token:
        raise HTTPException(
            status_code=401,
            detail={
                'status': 'error',
                'errors': [
                    {'location': 'body', 'name': 'user', 'description': 'Login failed'}
                ],
            },
        )

    # user is not None when token is truthy
    if user.tos_validated is None and body.accept_tos is not True:
        raise HTTPException(
            status_code=403,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'Forbidden',
                        'description': ('Terms of Service need to be accepted'),
                    }
                ],
            },
        )

    if user.tos_validated is None and body.accept_tos is True:
        try:
            db.execute(
                User.__table__.update()
                .where(User.id == user.id)
                .values(tos_validated=datetime.now(timezone.utc))
            )
            db.flush()
        except Exception:
            log.warning('Error persisting user', exc_info=True)
            raise HTTPException(status_code=500, detail='Error persisting user')

    response = _token_to_response(user, token)

    if body.discourse:
        client = get_discourse_client(_settings)
        try:
            if body.sso and body.sig:
                redirect = client.redirect(user, body.sso, body.sig)
                response['redirect'] = redirect
            else:
                r = client.redirect_without_nonce(user)
                response['redirect_internal'] = r
        except Exception:
            log.warning('Error logging into discourse for %d', user.id, exc_info=True)
    return response


# ── POST /renew ──────────────────────────────────────────────


@router.post('/renew')
def renew(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = _renew_token(user, request, db)
    if token:
        return _token_to_response(user, token)
    raise HTTPException(status_code=500, detail='Error renewing token')


# ── POST /logout ─────────────────────────────────────────────


@router.post('/logout')
def logout(
    body: LogoutBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = {'user': user.id}
    token_str = _extract_token(request)
    if token_str:
        remove_token(token_str, session=db)
    if body.discourse:
        try:
            client = get_discourse_client(_settings)
            result['logged_out_discourse_user'] = client.logout(user.id)
        except Exception:
            log.warning('Error logging out of discourse for %d', user.id, exc_info=True)
    return result


# ── POST /request_password_change ────────────────────────────


@router.post('/request_password_change')
def request_password_change(
    body: RequestPasswordChangeBody, db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'email',
                        'description': 'No user with this email',
                    }
                ],
            },
        )
    if user.blocked:
        raise HTTPException(
            status_code=403,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'Forbidden',
                        'description': 'account blocked',
                    }
                ],
            },
        )

    user.update_validation_nonce(Purpose.new_password, VALIDATION_EXPIRE_DAYS)
    try:
        db.flush()
    except Exception:
        log.warning('Error persisting user', exc_info=True)
        raise HTTPException(status_code=500, detail='Error persisting user')

    svc = get_email_service_from_settings(_settings)
    nonce = user.validation_nonce
    link = _settings['mail.request_password_change_url_template'].format('#', nonce)
    svc.send_request_change_password(user, link)
    return {}


# ── POST /validate_new_password/{nonce} ──────────────────────


@router.post('/validate_new_password/{nonce}')
def validate_new_password(
    nonce: str, body: PasswordBody, db: Session = Depends(get_db)
):
    ec = _ErrorCollector()
    encoded_pw = _validate_password(body.password, ec)
    _raise_errors(ec)

    user = _validate_user_from_nonce(Purpose.new_password, nonce, db)
    user.password = encoded_pw

    resp = _log_and_build_token_response(user, db)
    if resp:
        try:
            client = get_discourse_client(_settings)
            r = client.redirect_without_nonce(user)
            resp['redirect_internal'] = r
        except Exception:
            log.error('Error logging into discourse for %d', user.id, exc_info=True)
        user.clear_validation_nonce()
        try:
            db.flush()
        except Exception:
            log.warning('Error persisting user', exc_info=True)
            raise HTTPException(status_code=500, detail='Error persisting user')
        return resp

    raise HTTPException(
        status_code=403,
        detail={
            'status': 'error',
            'errors': [
                {'location': 'body', 'name': 'user', 'description': 'Login failed'}
            ],
        },
    )


# ── POST /validate_register_email/{nonce} ────────────────────


@router.post('/validate_register_email/{nonce}')
def validate_register_email(nonce: str, db: Session = Depends(get_db)):
    user = _validate_user_from_nonce(Purpose.registration, nonce, db)
    user.clear_validation_nonce()
    user.email_validated = True

    try:
        from c2corg_api.search import get_queue_config

        qc = get_queue_config(_settings)
        notify_es_syncer(qc)
    except Exception:
        log.warning('Could not notify ES syncer', exc_info=True)

    resp = _log_and_build_token_response(user, db)
    if resp:
        try:
            client = get_discourse_client(_settings)
            r = client.redirect_without_nonce(user)
            resp['redirect_internal'] = r
        except Exception:
            log.error('Error logging into discourse for %d', user.id, exc_info=True)
            raise HTTPException(status_code=500, detail='Error with Discourse')
        try:
            db.flush()
        except Exception:
            log.warning('Error persisting user', exc_info=True)
            raise HTTPException(status_code=500, detail='Error persisting user')
        return resp

    raise HTTPException(
        status_code=403,
        detail={
            'status': 'error',
            'errors': [
                {'location': 'body', 'name': 'user', 'description': 'Login failed'}
            ],
        },
    )


# ── POST /validate_change_email/{nonce} ──────────────────────


@router.post('/validate_change_email/{nonce}')
def validate_change_email(nonce: str, db: Session = Depends(get_db)):
    user = _validate_user_from_nonce(Purpose.change_email, nonce, db)
    user.clear_validation_nonce()
    user.email = user.email_to_validate  # type: ignore[assignment]
    user.email_to_validate = None

    try:
        client = get_discourse_client(_settings)
        client.sync_sso(user)
    except Exception:
        log.error('Error syncing email with discourse', exc_info=True)
        raise HTTPException(status_code=500, detail='Error with Discourse')
    try:
        db.flush()
    except Exception:
        log.warning('Error persisting user', exc_info=True)
        raise HTTPException(status_code=500, detail='Error persisting user')
    return {}
