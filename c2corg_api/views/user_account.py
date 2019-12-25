import logging

import colander
from c2corg_api import DBSession
from c2corg_api.emails.email_service import get_email_service
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.user import User, Purpose
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import cors_policy, restricted_json_view, restricted_view
from c2corg_api.views.user import is_unused_user_attribute, ENCODING, \
    VALIDATION_EXPIRE_DAYS, validate_forum_username
from c2corg_common.attributes import default_langs
from cornice.resource import resource
from cornice.validators import colander_body_validator
from functools import partial
from pyramid.httpexceptions import HTTPInternalServerError

log = logging.getLogger(__name__)


class UpdatePreferredLangSchema(colander.MappingSchema):
    lang = colander.SchemaNode(
            colander.String(),
            validator=colander.OneOf(default_langs))


@resource(path='/users/update_preferred_language', cors_policy=cors_policy)
class UserPreferredLanguageRest(object):
    schema = UpdatePreferredLangSchema()

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        renderer='json', schema=schema, validators=[colander_body_validator])
    def post(self):
        request = self.request
        userid = request.authenticated_userid
        user = DBSession.query(User).get(userid)
        user.lang = request.validated['lang']
        return {}


class UpdateAccountSchema(colander.MappingSchema):
    email = colander.SchemaNode(
            colander.String(),
            missing=colander.drop,
            validator=colander.All(
                colander.Email(),
                colander.Function(
                    partial(is_unused_user_attribute, 'email'),
                    'Already used email'
                )
            ))
    name = colander.SchemaNode(
            colander.String(),
            missing=colander.drop,
            validator=colander.Length(min=3))
    forum_username = colander.SchemaNode(
            colander.String(),
            missing=colander.drop,
            validator=colander.All(
                colander.Length(max=25),
                colander.Function(
                    partial(is_unused_user_attribute,
                            'forum_username',
                            lowercase=True),
                    'Already used forum name'
                )
            ))
    currentpassword = colander.SchemaNode(
            colander.String(encoding=ENCODING),
            validator=colander.Length(min=3))
    newpassword = colander.SchemaNode(
            colander.String(encoding=ENCODING),
            missing=colander.drop,
            validator=colander.Length(min=3))

    is_profile_public = colander.SchemaNode(
            colander.Boolean(),
            missing=colander.drop)


@resource(path='/users/account', cors_policy=cors_policy)
class UserAccountRest(object):
    updateschema = UpdateAccountSchema()

    def __init__(self, request):
        self.request = request

    def get_user(self):
        userid = self.request.authenticated_userid
        return DBSession.query(User).get(userid)

    @restricted_view(renderer='json', http_cache=0)
    def get(self):
        user = self.get_user()
        return {
            'email': user.email,
            'name': user.name,
            'forum_username': user.forum_username,
            'is_profile_public': user.is_profile_public
        }

    @restricted_json_view(
        renderer='json',
        schema=updateschema,
        validators=[colander_body_validator,
                    validate_forum_username])
    def post(self):
        user = self.get_user()
        request = self.request
        validated = request.validated

        result = {}

        # Before all, check whether the user knows the current password
        current_password = validated['currentpassword']
        if not user.validate_password(current_password):
            request.errors.add('body', 'currentpassword', 'Invalid password')
            return

        sync_sso = False

        # update password if a new password is provided
        if 'newpassword' in validated:
            user.password = validated['newpassword']

        # start email validation procedure if a new email is provided
        email_link = None
        if 'email' in validated and validated['email'] != user.email:
            user.email_to_validate = validated['email']
            user.update_validation_nonce(
                    Purpose.change_email,
                    VALIDATION_EXPIRE_DAYS)
            email_service = get_email_service(self.request)
            nonce = user.validation_nonce
            settings = request.registry.settings
            link = settings['mail.validate_change_email_url_template'].format(
                '#', nonce)
            email_link = link
            result['email'] = validated['email']
            result['sent_email'] = True
            sync_sso = True

        update_search_index = False
        if 'name' in validated:
            user.name = validated['name']
            result['name'] = user.name
            update_search_index = True
            sync_sso = True

        if 'forum_username' in validated:
            user.forum_username = validated['forum_username']
            result['forum_username'] = user.forum_username
            update_search_index = True
            sync_sso = True

        if 'is_profile_public' in validated:
            user.is_profile_public = validated['is_profile_public']

        # Synchronize everything except the new email (still stored
        # in the email_to_validate attribute while validation is pending).
        if sync_sso:
            try:
                client = get_discourse_client(request.registry.settings)
                client.sync_sso(user)
            except:  # noqa
                log.error('Error syncing with discourse', exc_info=True)
                raise HTTPInternalServerError('Error with Discourse')

        try:
            DBSession.flush()
        except:  # noqa
            log.warning('Error persisting user', exc_info=True)
            raise HTTPInternalServerError('Error persisting user')

        if email_link:
            email_service.send_change_email_confirmation(user, link)

        if update_search_index:
            # when user name changes, the search index has to be updated
            notify_es_syncer(self.request.registry.queue_config)

            # also update the cache version of the user profile
            update_cache_version(user.profile)

        return result
