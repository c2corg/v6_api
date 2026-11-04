"""Schemas of the user accounts."""

import re

from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.user import User
from c2corg_api.schemas.base import ModelSchema, Schema
from c2corg_api.schemas.types import Bool, Int, OneOf, Str, email_check

# the length of a forum username, checked by the schema before its format
FORUM_USERNAME_LENGTH = {'min_length': 3, 'max_length': 25}


def forum_username_check(value):
    """Check the format of a forum username, as Discourse accepts it."""
    # the length is checked by the schema (Str): one message at a time
    if not 3 <= len(value) <= 25:
        return None
    if re.search(r'[^\w.-]', value):
        return 'Contain invalid character(s)'
    if re.match(r'\W', value[0]):
        return 'First character is invalid'
    if re.match(r'[^A-Za-z0-9]', value[-1]):
        return 'Last character is invalid'
    if re.search(r'[-_\.]{2,}', value):
        return 'Contains consecutive special characters'
    if re.search(
        r'\.(js|json|css|htm|html|xml|jpg|jpeg|png|gif|bmp|ico|tif|tiff|woff)$',
        value,
    ):
        return 'Ended by confusing suffix'
    return None


class UserCreateSchema(Schema):
    # the password is checked by validate_json_password
    username: Str(200)
    forum_username: Str(**FORUM_USERNAME_LENGTH, checks=[forum_username_check])
    name: Str(200)
    # no length check here: Colander's Email validator replaced it
    email: Str(checks=[email_check])
    lang: OneOf(default_langs) = 'fr'


class UserSchema(Schema):
    id: Int = None
    username: Str(200)
    forum_username: Str(25)
    name: Str(200)
    email: Str(200)
    email_validated: Bool = False
    moderator: Bool = False


user_create_schema = ModelSchema(User, UserCreateSchema)
user_schema = ModelSchema(User, UserSchema)
