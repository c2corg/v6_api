import logging

from pydantic import BaseModel, field_validator
from typing import Optional
from c2corg_api.security.acl import ACLDefault
from c2corg_api import DBSession
from c2corg_api.emails.email_service import get_email_service
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.user import User, Purpose
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import cors_policy, restricted_json_view, restricted_view
from c2corg_api.views.user import is_unused_user_attribute, \
    VALIDATION_EXPIRE_DAYS, validate_forum_username
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.views.pydantic_validator import make_pydantic_validator
from cornice.resource import resource
from pyramid.httpexceptions import HTTPInternalServerError

log = logging.getLogger(__name__)


class UpdatePreferredLangSchema(BaseModel):
    lang: str

    @field_validator('lang')
    @classmethod
    def lang_must_be_valid(cls, v):
        if v not in default_langs:
            raise ValueError('must be one of {}'.format(default_langs))
        return v


@resource(path='/users/update_preferred_language', cors_policy=cors_policy)
class UserPreferredLanguageRest(ACLDefault):

    @restricted_json_view(
        renderer='json',
        validators=[make_pydantic_validator(UpdatePreferredLangSchema)])
    def post(self):
        request = self.request
        userid = request.authenticated_userid
        user = DBSession.get(User, userid)
        user.lang = request.validated['lang']
        return {}


class UpdateAccountSchema(BaseModel):
    currentpassword: str
    email: Optional[str] = None
    name: Optional[str] = None
    forum_username: Optional[str] = None
    newpassword: Optional[str] = None
    is_profile_public: Optional[bool] = None


def validate_account_fields(request, **kwargs):
    """Validate account update fields after pydantic parsing."""
    validated = request.validated

    currentpassword = validated.get('currentpassword')
    if currentpassword is not None and len(currentpassword) < 3:
        request.errors.add('body', 'currentpassword',
                           'Shorter than minimum length 3')

    email = validated.get('email')
    if email is not None:
        if '@' not in email:
            request.errors.add('body', 'email', 'Invalid email')
        elif not is_unused_user_attribute('email', email):
            request.errors.add('body', 'email', 'Already used email')

    name = validated.get('name')
    if name is not None and len(name) < 3:
        request.errors.add('body', 'name', 'Shorter than minimum length 3')

    forum_username = validated.get('forum_username')
    if forum_username is not None:
        if not is_unused_user_attribute(
                'forum_username', forum_username, lowercase=True):
            request.errors.add('body', 'forum_username',
                               'Already used forum name')

    newpassword = validated.get('newpassword')
    if newpassword is not None and len(newpassword) < 3:
        request.errors.add('body', 'newpassword',
                           'Shorter than minimum length 3')


@resource(path='/users/account', cors_policy=cors_policy)
class UserAccountRest(ACLDefault):

    def get_user(self):
        userid = self.request.authenticated_userid
        return DBSession.get(User, userid)

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
        validators=[make_pydantic_validator(UpdateAccountSchema),
                    validate_account_fields,
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
            except Exception:
                log.error('Error syncing with discourse', exc_info=True)
                raise HTTPInternalServerError('Error with Discourse')

        try:
            DBSession.flush()
        except Exception:
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
