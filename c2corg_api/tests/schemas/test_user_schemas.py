from functools import partial

import colander

from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.user import User, schema_create_user, schema_user
from c2corg_api.schemas.user import UserCreateSchema, user_create_schema, user_schema
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.schemas.parity import assert_parity
from c2corg_api.views import serialize
from c2corg_api.views.sso import SsoLoginSchema, SsoSyncSchema
from c2corg_api.views.user import (
    MINIMUM_PASSWORD_LENGTH,
    PASSWORD_STRENGTH_ERROR,
    DiscourseRedirectSchema,
    LoginSchema,
    is_password_strong_enough,
    is_unused_user_attribute,
)
from c2corg_api.views.user_account import (
    UpdateAccountSchema,
    UpdatePreferredLangSchema,
)


def _string(**kwargs):
    return colander.SchemaNode(colander.String(), **kwargs)


# the Colander schemas these replace, as they were defined in the views
class ColanderLogin(colander.MappingSchema):
    username = _string()
    password = _string()
    accept_tos = colander.SchemaNode(colander.Boolean(), missing=False)


class ColanderDiscourseRedirect(colander.MappingSchema):
    sso = _string()
    sig = _string()


class ColanderPreferredLang(colander.MappingSchema):
    lang = _string(validator=colander.OneOf(default_langs))


class ColanderSsoSync(colander.MappingSchema):
    sso_key = _string()
    external_id = _string()
    email = _string(missing=None)
    username = _string(missing=None)
    name = _string(missing=None)
    forum_username = _string(missing=None)
    lang = _string(validator=colander.OneOf(default_langs), missing=None)
    groups = _string(missing=None)


class ColanderSsoLogin(colander.MappingSchema):
    token = _string()


class ColanderUpdateAccount(colander.MappingSchema):
    email = _string(
        missing=colander.drop,
        validator=colander.All(
            colander.Email(),
            colander.Function(
                partial(is_unused_user_attribute, 'email'), 'Already used email'
            ),
        ),
    )
    name = _string(missing=colander.drop, validator=colander.Length(min=3))
    forum_username = _string(
        missing=colander.drop,
        validator=colander.All(
            colander.Length(max=25),
            colander.Function(
                partial(is_unused_user_attribute, 'forum_username', lowercase=True),
                'Already used forum name',
            ),
        ),
    )
    currentpassword = _string(validator=colander.Length(min=1))
    newpassword = _string(
        missing=colander.drop,
        validator=colander.All(
            colander.Length(min=MINIMUM_PASSWORD_LENGTH),
            colander.Function(is_password_strong_enough, PASSWORD_STRENGTH_ERROR),
        ),
    )
    is_profile_public = colander.SchemaNode(colander.Boolean(), missing=colander.drop)


def test_user_create_parity():
    assert_parity(schema_create_user, UserCreateSchema)
    data = schema_create_user.deserialize(
        {
            'username': 'u',
            'forum_username': 'f',
            'name': 'n',
            'email': 'u@example.org',
        }
    )
    expected = schema_create_user.objectify(data)
    actual = user_create_schema.objectify(data)
    for name in ('username', 'forum_username', 'name', 'email', 'lang'):
        assert getattr(actual, name) == getattr(expected, name)


def test_user_dictify():
    user = User(id=1, username='u', forum_username='f', name='n', email='e@x.org')
    assert serialize(user_schema.dictify(user)) == serialize(schema_user.dictify(user))


def test_body_schemas_parity():
    for colander_schema, schema in (
        (ColanderLogin(), LoginSchema),
        (ColanderDiscourseRedirect(), DiscourseRedirectSchema),
        (ColanderPreferredLang(), UpdatePreferredLangSchema),
        (ColanderSsoSync(), SsoSyncSchema),
        (ColanderSsoLogin(), SsoLoginSchema),
    ):
        assert_parity(colander_schema, schema)


class TestUpdateAccountParity(BaseTestCase):
    def test_update_account_parity(self):
        # the email and forum name checks query the users
        assert_parity(
            ColanderUpdateAccount(),
            UpdateAccountSchema,
            extra_cases=[
                {'currentpassword': 'x', 'email': 'contributor@camptocamp.org'},
                {'currentpassword': 'x', 'forum_username': 'Contributor'},
                {'currentpassword': 'x', 'newpassword': 'weak'},
                {'currentpassword': 'x', 'newpassword': 'Strong$Password1'},
                {'currentpassword': 'x', 'email': 'bad', 'name': 'ab'},
            ],
        )
