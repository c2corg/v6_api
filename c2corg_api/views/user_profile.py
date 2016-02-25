
from c2corg_api.models.user_profile import schema_update_user_profile, \
    UserProfile, schema_user_profile
from cornice.resource import resource

from c2corg_api.views.document import DocumentRest
from c2corg_api.views import cors_policy, restricted_json_view, restricted_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param
from pyramid.httpexceptions import HTTPForbidden


@resource(collection_path='/profiles', path='/profiles/{id}',
          cors_policy=cors_policy)
class UserProfileRest(DocumentRest):

    @restricted_view(
        validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(UserProfile, schema_user_profile)

    @restricted_view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(UserProfile, schema_user_profile)

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

        return self._put(UserProfile, schema_user_profile)
