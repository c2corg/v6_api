from functools import partial
from pyramid.httpexceptions import HTTPInternalServerError

from cornice.resource import resource, view

from c2corg_api.models.user import User, schema_user, schema_create_user
from c2corg_api.views import (
        cors_policy, json_view, to_json_dict)
from c2corg_api.views.validation import validate_id

from c2corg_api.models import DBSession

from c2corg_api.security.roles import try_login

import colander

ENCODING = 'UTF-8'


def validate_json_password(request):
    """Checks if the password was given and encodes it.
       This is done here as the password is not an SQLAlchemy field.
       In addition, we can ensure the password is not leaked in the
       validation error messages.
    """

    if 'password' not in request.json:
        request.errors.add('user', 'password', 'Required')

    try:
        # We receive a unicode string. The hashing function used
        # later on requires plain string otherwise it raises
        # the "Unicode-objects must be encoded before hashing" error.
        password = request.json['password']
        request.validated['password'] = password.encode(ENCODING)
    except:
        request.errors.add('user', 'password', 'Invalid')


def validate_unique_attribute(attrname, request):
    """Checks if the given attribute is unique.
    """

    if attrname in request.json:
        value = request.json[attrname]
        attr = getattr(User, attrname)
        count = DBSession.query(User).filter(attr == value).count()
        if count == 0:
            request.validated[attrname] = value
        else:
            request.errors.add('user', attrname, 'already used ' + attrname)


@resource(path='/users/{id}', cors_policy=cors_policy)
class UserRest(object):
    def __init__(self, request):
        self.request = request

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']
        user = DBSession. \
            query(User). \
            filter(User.id == id). \
            first()

        return to_json_dict(user, schema_user)


@resource(path='/users/register', cors_policy=cors_policy)
class UserRegistrationRest(object):
    def __init__(self, request):
        self.request = request

    @json_view(schema=schema_create_user, validators=[
        validate_json_password,
        partial(validate_unique_attribute, "email"),
        partial(validate_unique_attribute, "username")])
    def post(self):
        user = schema_create_user.objectify(self.request.validated)
        user.password = self.request.validated['password']

        DBSession.add(user)
        try:
            DBSession.flush()
        except:
            # TODO: log the error for debugging
            raise HTTPInternalServerError('Error persisting user')

        return to_json_dict(user, schema_user)


class LoginSchema(colander.MappingSchema):
    username = colander.SchemaNode(colander.String())
    password = colander.SchemaNode(colander.String())

login_schema = LoginSchema()


@resource(path='/users/login', cors_policy=cors_policy)
class UserLoginRest(object):
    def __init__(self, request):
        self.request = request

    @json_view(schema=login_schema, validators=[validate_json_password])
    def post(self):
        request = self.request
        username = request.validated['username']
        password = request.validated['password']
        token = try_login(username, password, request)
        if token:
            return {
                'token': token
            }
        else:
            request.errors.status = 401
            request.errors.add('body', 'user', 'Login failed')
