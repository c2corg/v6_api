import logging
from functools import partial

from c2corg_api import DBSession
from c2corg_api.emails.email_service import get_email_service
from c2corg_api.httpexceptions import HTTPInternalServerError
from c2corg_api.models.cache_version import update_cache_version
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.user import Purpose, User
from c2corg_api.schemas.base import DROP, Schema, body_validator
from c2corg_api.schemas.types import Bool, OneOf, Str, email_check, function_check
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.security.acl import ACLDefault
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import restricted_json_view, restricted_view
from c2corg_api.views.resource import resource
from c2corg_api.views.user import (
    MINIMUM_PASSWORD_LENGTH,
    PASSWORD_STRENGTH_ERROR,
    VALIDATION_EXPIRE_DAYS,
    is_password_strong_enough,
    is_unused_user_attribute,
    validate_forum_username,
)

log = logging.getLogger(__name__)


class UpdatePreferredLangSchema(Schema):
    lang: OneOf(default_langs)


@resource(path='/users/update_preferred_language')
class UserPreferredLanguageRest(ACLDefault):
    @restricted_json_view(
        renderer='json', validators=[body_validator(UpdatePreferredLangSchema)]
    )
    def post(self):
        request = self.request
        userid = request.authenticated_userid
        user = DBSession.get(User, userid)
        user.lang = request.validated['lang']
        return {}


class UpdateAccountSchema(Schema):
    email: Str(
        checks=[
            email_check,
            function_check(
                partial(is_unused_user_attribute, 'email'), 'Already used email'
            ),
        ]
    ) = DROP
    name: Str(min_length=3) = DROP
    forum_username: Str(
        max_length=25,
        checks=[
            function_check(
                partial(is_unused_user_attribute, 'forum_username', lowercase=True),
                'Already used forum name',
            )
        ],
    ) = DROP
    # Verifies an *existing* credential, so it must accept whatever was
    # valid when the account was created (e.g. under a looser, older
    # policy) - just needs to be non-empty, not held to today's policy.
    currentpassword: Str(min_length=1)
    # A *new* password being set: held to the current policy.
    newpassword: Str(
        min_length=MINIMUM_PASSWORD_LENGTH,
        checks=[function_check(is_password_strong_enough, PASSWORD_STRENGTH_ERROR)],
    ) = DROP

    is_profile_public: Bool = DROP


@resource(path='/users/account')
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
            'is_profile_public': user.is_profile_public,
        }

    @restricted_json_view(
        renderer='json',
        validators=[body_validator(UpdateAccountSchema), validate_forum_username],
    )
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
            user.update_validation_nonce(Purpose.change_email, VALIDATION_EXPIRE_DAYS)
            email_service = get_email_service(self.request)
            nonce = user.validation_nonce
            settings = request.registry.settings
            link = settings['mail.validate_change_email_url_template'].format(
                '#', nonce
            )
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
            except Exception as e:
                log.error('Error syncing with discourse', exc_info=True)
                raise HTTPInternalServerError('Error with Discourse') from e

        try:
            DBSession.flush()
        except Exception as e:
            log.warning('Error persisting user', exc_info=True)
            raise HTTPInternalServerError('Error persisting user') from e

        if email_link:
            email_service.send_change_email_confirmation(user, link)

        if update_search_index:
            # when user name changes, the search index has to be updated
            notify_es_syncer(self.request.registry.queue_config)

            # also update the cache version of the user profile
            update_cache_version(user.profile)

        return result
