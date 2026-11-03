from sqlalchemy.orm import load_only

from c2corg_api.httpexceptions import HTTPForbidden, HTTPNotFound
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.user_profile import (
    UserProfileUpdateSchema,
    internal_user_profile_schema,
    user_profile_schema,
)
from c2corg_api.views import restricted_json_view, restricted_view
from c2corg_api.views.document import (
    collection_get,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import user_profile_documents_config
from c2corg_api.views.resource import view
from c2corg_api.views.validation import (
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)


@restricted_json_view(
    validators=[body_validator(UserProfileUpdateSchema), validate_id],
)
def update_user_profile(request):
    if not request.has_permission('moderator'):
        # moderators can change the profile of every user
        if request.authenticated_userid != request.validated['id']:
            # but a normal user can only change its own profile
            raise HTTPForbidden('No permission to change this user profile')

    reset_title(request)

    return put_document(request, UserProfile, internal_user_profile_schema)


@restricted_view(validators=[validate_pagination, validate_preferred_lang_param])
def list_user_profiles(request):
    return collection_get(request, USERPROFILE_TYPE, user_profile_documents_config)


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_user_profile(request):
    # load the requested user
    requested_user_id = request.validated['id']
    requested_user = (
        DBSession.query(User)
        .filter(User.id == requested_user_id)
        .filter(User.email_validated)
        .options(load_only(User.id, User.is_profile_public, User.name))
        .first()
    )

    if not requested_user:
        raise HTTPNotFound('user not found')
    elif requested_user.is_profile_public or request.has_permission('authenticated'):
        # only show the full profile if authenticated or if the user marked
        # the profile as public
        return read_document(
            request, user_profile_documents_config, user_profile_schema
        )
    else:
        # otherwise only return the user name
        return {
            'not_authorized': True,
            'document_id': requested_user.id,
            'name': requested_user.name,
        }


@view(validators=[validate_id, validate_lang])
def get_user_profile_info(request):
    return document_info(request, user_profile_documents_config)


def reset_title(request):
    """Set the title of the user profile of a request to an empty string."""
    # The title of user profile documents is left empty. Because the title
    # must be non-null it is set to an empty string though.
    document = request.validated['document']
    locales = document.get('locales')
    if locales:
        for locale in locales:
            locale['title'] = ''
