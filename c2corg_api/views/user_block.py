import logging

from c2corg_api import DBSession
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import user_profile_documents_config
from c2corg_api.views.validation import validate_id, \
    validate_body_user_id
from colander import MappingSchema, SchemaNode, Integer, required
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError

log = logging.getLogger(__name__)


class BlockSchema(MappingSchema):
    user_id = SchemaNode(Integer(), missing=required)


def _get_user(user_id):
    user = DBSession.query(User).get(user_id)

    if not user:
        raise HTTPBadRequest('Unknown user {}'.format(user_id))

    return user


@resource(path='/users/block', cors_policy=cors_policy)
class UserBlockRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=BlockSchema(),
        validators=[colander_body_validator, validate_body_user_id])
    def post(self):
        """ Block the given user.

        Request:
            `POST` `/users/block`

        Request body:
            {'user_id': @user_id@}

        """
        user = _get_user(self.request.validated['user_id'])
        user.blocked = True

        # suspend account in Discourse (suspending an account prevents a login)
        try:
            client = get_discourse_client(self.request.registry.settings)
            block_duration = 99999  # 99999 days = 273 years
            client.suspend(
                user.id, block_duration, 'account blocked by moderator')
        except:
            log.error(
                'Suspending account in Discourse failed: %d', user.id,
                exc_info=True)
            raise HTTPInternalServerError(
                'Suspending account in Discourse failed')

        return {}


@resource(path='/users/unblock', cors_policy=cors_policy)
class UserUnblockRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=BlockSchema(),
        validators=[colander_body_validator, validate_body_user_id])
    def post(self):
        """ Unblock the given user.

        Request:
            `POST` `/users/unblock`

        Request body:
            {'user_id': @user_id@}

        """
        user = _get_user(self.request.validated['user_id'])
        user.blocked = False

        # unsuspend account in Discourse
        try:
            client = get_discourse_client(self.request.registry.settings)
            client.unsuspend(user.id)
        except:
            log.error(
                'Unsuspending account in Discourse failed: %d', user.id,
                exc_info=True)
            raise HTTPInternalServerError(
                'Unsuspending account in Discourse failed')

        return {}


@resource(path='/users/blocked/{id}', cors_policy=cors_policy)
class UserBlockedRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(permission='moderator', validators=[validate_id])
    def get(self):
        """ Check if the given user is blocked.

        Request:
            `GET` `users/blocked/{user_id}`

        Example response:

            {'blocked': true}

        """
        user = _get_user(self.request.validated['id'])

        return {
            'blocked': user.blocked
        }


@resource(path='/users/blocked', cors_policy=cors_policy)
class UserBlockedAllRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(permission='moderator')
    def get(self):
        """ Get the blocked users.

        Request:
            `GET` `/users/blocked`

        Example response:

            {
                'blocked': [
                    {
                        'document_id': 123,
                        ...
                    }
                ]
            }
        """
        blocked_user_ids = DBSession. \
            query(User.id). \
            filter(User.blocked). \
            all()
        blocked_user_ids = [user_id for (user_id, ) in blocked_user_ids]

        blocked_users = get_documents_for_ids(
            blocked_user_ids, None, user_profile_documents_config). \
            get('documents')

        return {
            'blocked': blocked_users
        }
