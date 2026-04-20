"""
SSO token / time helpers.

Extracted from ``c2corg_api.views.sso``.
"""

from base64 import b64encode
from datetime import datetime, timedelta, timezone
from os import urandom

CONST_EXPIRE_AFTER_MINUTES = 10


def generate_token():
    return b64encode(urandom(64)).decode('utf-8')


def localized_now():
    return datetime.now(timezone.utc)


def sso_expire_from_now():
    return localized_now() + timedelta(minutes=CONST_EXPIRE_AFTER_MINUTES)
