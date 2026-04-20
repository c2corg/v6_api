"""
User validation helpers.

Extracted from ``c2corg_api.views.user``.
"""

import re

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func

from c2corg_api.models.user import User
from c2corg_api.routers.helpers._db_compat import resolve_db

ENCODING = 'UTF-8'
VALIDATION_EXPIRE_DAYS = 3
MINIMUM_PASSWORD_LENGTH = 3


def is_valid_email(email):
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return False
    return True


def is_unused_user_attribute(attrname, value, lowercase=False, db=None):
    db = resolve_db(db)
    attr = getattr(User, attrname)
    query = db.query(User)
    if lowercase:
        query = query.filter(func.lower(attr) == value.lower())
    else:
        query = query.filter(attr == value)
    return query.count() == 0


def check_forum_username(value):
    """Validate a Discourse forum username."""
    if len(value) < 3:
        return 'Shorter than minimum length 3'
    if len(value) > 25:
        return 'Longer than maximum length 25'
    if re.search(r'[^\w.-]', value):
        return 'Contain invalid character(s)'
    if re.match(r'\W', value[0]):
        return 'First character is invalid'
    if re.match(r'[^A-Za-z0-9]', value[-1]):
        return 'Last character is invalid'
    if re.search(r'[-_\.]{2,}', value):
        return 'Contains consecutive special characters'
    if re.search(
        (
            r'\.(js|json|css|htm|html|xml|jpg|jpeg|'
            r'png|gif|bmp|ico|tif|tiff|woff)$'
        ),
        value,
    ):
        return 'Ended by confusing suffix'
    return False
