"""Schemas of the user accounts."""

from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.user import User
from c2corg_api.schemas.base import ModelSchema, Schema
from c2corg_api.schemas.types import Bool, Int, OneOf, Str, email_check


class UserCreateSchema(Schema):
    # the password is checked by validate_json_password
    username: Str(200)
    forum_username: Str(25)
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
