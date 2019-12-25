from base64 import b64encode
from datetime import datetime, timedelta
from os import urandom
from pytz import utc
from urllib.parse import urlencode
import logging

import colander
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from pydiscourse.exceptions import DiscourseClientError
from pyramid.httpexceptions import (
    HTTPInternalServerError,
)

from c2corg_common.attributes import default_langs

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.sso import (
    SsoKey,
    SsoExternalId,
)
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.roles import log_validated_user_i_know_what_i_do
from c2corg_api.views import (
    cors_policy,
    json_view,
)
from c2corg_api.views.user import (
    token_to_response,
    validate_unique_attribute,
    validate_forum_username,
)

CONST_EXPIRE_AFTER_MINUTES = 10

log = logging.getLogger(__name__)


class SsoSyncSchema(colander.MappingSchema):
    sso_key = colander.SchemaNode(colander.String())
    external_id = colander.SchemaNode(colander.String())
    email = colander.SchemaNode(colander.String(),
                                missing=None)
    username = colander.SchemaNode(colander.String(),
                                   missing=None)
    name = colander.SchemaNode(colander.String(),
                               missing=None)
    forum_username = colander.SchemaNode(colander.String(),
                                         missing=None)
    lang = colander.SchemaNode(colander.String(),
                               validator=colander.OneOf(default_langs),
                               missing=None)
    groups = colander.SchemaNode(colander.String(),
                                 missing=None)


sso_sync_schema = SsoSyncSchema()


def sso_sync_validator(request, **kwargs):
    if 'sso_key' not in request.validated:
        return  # validated by colander schema
    sso_key = DBSession.query(SsoKey). \
        filter(SsoKey.key == request.validated['sso_key']). \
        one_or_none()
    if sso_key is None:
        log.warning('Attempt to use sso_sync with bad key from {}'
                    .format(request.client_addr))
        request.errors.status = 403
        request.errors.add('body', 'sso_key', 'Invalid')
        return

    user = None

    # search user by external_id
    if 'external_id' not in request.validated:
        return  # validated by colander schema
    sso_external_id = DBSession.query(SsoExternalId). \
        filter(SsoExternalId.domain == sso_key.domain). \
        filter(SsoExternalId.external_id ==
               request.validated['external_id']). \
        one_or_none()
    if sso_external_id is not None:
        user = sso_external_id.user

    if user is None:
        # search user by email
        if request.validated['email'] is None:
            request.errors.add('body', 'email', 'Required')
            return
        user = DBSession.query(User). \
            filter(User.email == request.validated['email']). \
            one_or_none()

    if user is None:
        username = request.validated['username']
        if username is None:
            request.errors.add('body', 'username', 'Required')
        request.validated['name'] = request.validated['name'] or username
        request.validated['forum_username'] = \
            request.validated['forum_username'] or username
        if request.validated['lang'] is None:
            request.errors.add('body', 'lang', 'Required')
        validate_unique_attribute('email', request, **kwargs)
        validate_unique_attribute('username', request, **kwargs)
        validate_forum_username(request, **kwargs)
        validate_unique_attribute(
            'forum_username', request, lowercase=True, **kwargs)

    request.validated['sso_key'] = sso_key
    request.validated['sso_external_id'] = sso_external_id
    request.validated['sso_user'] = user


@resource(path='/sso_sync', cors_policy=cors_policy)
class SsoSyncRest(object):
    def __init__(self, request):
        self.request = request

    @json_view(
        schema=sso_sync_schema,
        validators=[
            colander_body_validator,
            sso_sync_validator,
        ])
    def post(self):
        """
        Synchronize user details and return authentication url.
        Important: Email addresses need to be validated by external site.
        """
        request = self.request
        sso_key = request.validated['sso_key']
        sso_external_id = request.validated['sso_external_id']
        user = request.validated['sso_user']

        if user is None:
            # create new user
            user = User(
                username=request.validated['username'],
                name=request.validated['name'],
                forum_username=request.validated['forum_username'],
                email=request.validated['email'],
                email_validated=True,  # MUST be validated by external site
                lang=request.validated['lang'],
                password=generate_token()  # random password
            )
            # directly create the user profile, the document id of the profile
            # is the user id
            lang = user.lang
            user.profile = UserProfile(
                categories=['amateur'],
                locales=[DocumentLocale(lang=lang, title='')],
            )
            DBSession.add(user)
            DBSession.flush()

        if sso_external_id is None:
            sso_external_id = SsoExternalId(
                domain=sso_key.domain,
                external_id=request.validated['external_id'],
                user=user,
            )
            DBSession.add(sso_external_id)

        sso_external_id.token = generate_token()
        sso_external_id.expire = sso_expire_from_now()

        client = get_discourse_client(request.registry.settings)
        discourse_userid = call_discourse(
            get_discourse_userid, client, user.id)
        if discourse_userid is None:
            call_discourse(client.sync_sso, user)
            discourse_userid = client.get_userid(user.id)  # From cache

        # Groups are added to discourse, not removed
        group_ids = []
        discourse_groups = None
        groups = request.validated['groups'] or ''
        for group_name in groups.split(','):
            if group_name == '':
                continue
            group_id = None
            if discourse_groups is None:
                discourse_groups = call_discourse(client.client.groups)

            group_id = None
            for discourse_group in discourse_groups:
                if discourse_group['name'] == group_name:
                    group_id = discourse_group['id']

            if group_id is None:
                # If group is not found, we ignore it as we want to return
                # a valid token for user authentication
                pass
            else:
                group_ids.append(group_id)

        for group_id in group_ids:
            call_discourse(client.client.add_user_to_group,
                           group_id, discourse_userid)

        return {
            'url': '{}/sso-login?no_redirect&{}'.format(
                request.registry.settings['ui.url'],
                urlencode({'token': sso_external_id.token}))
        }


def get_discourse_userid(client, userid):
    """ Get discourse user id with 404 handling"""
    try:
        return client.get_userid(userid)
    except DiscourseClientError as e:
        if e.response.status_code == 404:
            return None
        raise


def call_discourse(method, *args, **kwargs):
    try:
        return method.__call__(*args, **kwargs)
    except Exception as e:
        log.error('Error with Discourse: {}'.format(str(e)), exc_info=True)
        raise HTTPInternalServerError('Error with Discourse')


def generate_token():
    return b64encode(urandom(64)).decode('utf-8')


def localized_now():
    return utc.localize(datetime.utcnow())


def sso_expire_from_now():
    return (localized_now() + timedelta(minutes=CONST_EXPIRE_AFTER_MINUTES))


class SsoLoginSchema(colander.MappingSchema):
    token = colander.SchemaNode(colander.String())


sso_login_schema = SsoLoginSchema()


def validate_token(request, **kwargs):
    if 'token' not in request.validated:
        return  # validated by colander schema

    sso_external_id = DBSession.query(SsoExternalId). \
        filter(SsoExternalId.token == request.validated['token']). \
        filter(SsoExternalId.expire > localized_now()). \
        one_or_none()
    if sso_external_id is None:
        log.warning('Attempt to use sso_login with bad token from {}'
                    .format(request.client_addr))
        request.errors.status = 403
        request.errors.add('body', 'token', 'Invalid')
        return
    request.validated['sso_user'] = sso_external_id.user


@resource(path='/sso_login', cors_policy=cors_policy)
class SsoLoginRest(object):
    def __init__(self, request):
        self.request = request

    @view(
        schema=sso_login_schema,
        validators=[colander_body_validator, validate_token])
    def post(self):
        user = self.request.validated['sso_user']
        token = log_validated_user_i_know_what_i_do(user, self.request)
        response = token_to_response(user, token, self.request)
        if 'discourse' in self.request.json:
            client = get_discourse_client(self.request.registry.settings)
            try:
                r = client.redirect_without_nonce(user)
                response['redirect_internal'] = r
            except:  # noqa
                # Any error with discourse should not prevent login
                log.warning(
                    'Error logging into discourse for %d', user.id,
                    exc_info=True)
        return response
