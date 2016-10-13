from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import schema_update_user_profile, \
    UserProfile, schema_user_profile, schema_internal_user_profile, \
    USERPROFILE_TYPE
from c2corg_api.views.document_schemas import user_profile_documents_config
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest
from c2corg_api.views import cors_policy, restricted_json_view, restricted_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param
from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound
from sqlalchemy.orm import load_only


@resource(collection_path='/profiles', path='/profiles/{id}',
          cors_policy=cors_policy)
class UserProfileRest(DocumentRest):

    @restricted_view(
        validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            USERPROFILE_TYPE, user_profile_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        # load the requested user
        requested_user_id = self.request.validated['id']
        requested_user = DBSession.query(User). \
            filter(User.id == requested_user_id). \
            filter(User.email_validated). \
            options(load_only(
                User.id, User.is_profile_public, User.name, User.username)). \
            first()

        if not requested_user:
            raise HTTPNotFound('user not found')
        elif requested_user.is_profile_public or \
                self.request.has_permission('authenticated'):
            # only show the full profile if authenticated or if the user marked
            # the profile as public
            return self._get(UserProfile, schema_user_profile)
        else:
            # otherwise only return the user name
            return {
                'not_authorized': True,
                'document_id': requested_user.id,
                'name': requested_user.name,
                'username': requested_user.username
            }

    @restricted_json_view(
            schema=schema_update_user_profile,
            validators=[validate_id])
    def put(self):
        if not self.request.has_permission('moderator'):
            # moderators can change the profile of every user
            if self.request.authenticated_userid != \
                    self.request.validated['id']:
                # but a normal user can only change its own profile
                raise HTTPForbidden(
                    'No permission to change this user profile')

        self._reset_title()

        return self._put(UserProfile, schema_internal_user_profile)

    def _reset_title(self):
        """The title of user profile documents is left empty. Because the title
        must be non-null it is set to an empty string though.
        """
        document = self.request.validated['document']
        locales = document.get('locales')
        if locales:
            for locale in locales:
                locale['title'] = ''
