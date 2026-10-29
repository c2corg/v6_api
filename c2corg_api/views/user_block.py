import logging

from c2corg_api import DBSession
from c2corg_api.httpexceptions import HTTPBadRequest, HTTPInternalServerError
from c2corg_api.models.user import User
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int
from c2corg_api.security.acl import ACLDefault
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import user_profile_documents_config
from c2corg_api.views.resource import resource
from c2corg_api.views.validation import validate_body_user_id, validate_id

log = logging.getLogger(__name__)


class BlockSchema(Schema):
    user_id: Int


def _get_user(user_id):
    user = DBSession.get(User, user_id)

    if not user:
        raise HTTPBadRequest(f'Unknown user {user_id}')

    return user


@resource(path='/users/block')
class UserBlockRest(ACLDefault):
    @restricted_json_view(
        permission='moderator',
        validators=[body_validator(BlockSchema), validate_body_user_id],
    )
    def post(self):
        """Block the given user.

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
            client.suspend(user.id, block_duration, 'account blocked by moderator')
        except Exception as e:
            log.error(
                'Suspending account in Discourse failed: %d', user.id, exc_info=True
            )
            raise HTTPInternalServerError(
                'Suspending account in Discourse failed'
            ) from e

        return {}


@resource(path='/users/unblock')
class UserUnblockRest(ACLDefault):
    @restricted_json_view(
        permission='moderator',
        validators=[body_validator(BlockSchema), validate_body_user_id],
    )
    def post(self):
        """Unblock the given user.

        Request:
            `POST` `/users/unblock`

        Request body:
            {'user_id': @user_id@}

        """
        user = _get_user(self.request.validated['user_id'])
        user.blocked = False
        # Make sure the rate limiting counter is reset
        # (it might be the reason the user was blocked):
        user.ratelimit_times = 0

        # unsuspend account in Discourse
        try:
            client = get_discourse_client(self.request.registry.settings)
            client.unsuspend(user.id)
        except Exception as e:
            log.error(
                'Unsuspending account in Discourse failed: %d', user.id, exc_info=True
            )
            raise HTTPInternalServerError(
                'Unsuspending account in Discourse failed'
            ) from e

        return {}


@resource(path='/users/blocked/{id}')
class UserBlockedRest(ACLDefault):
    @restricted_json_view(permission='moderator', validators=[validate_id])
    def get(self):
        """Check if the given user is blocked.

        Request:
            `GET` `users/blocked/{user_id}`

        Example response:

            {'blocked': true}

        """
        user = _get_user(self.request.validated['id'])

        return {'blocked': user.blocked}


@resource(path='/users/blocked')
class UserBlockedAllRest(ACLDefault):
    @restricted_json_view(permission='moderator')
    def get(self):
        """Get the blocked users.

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
        blocked_user_ids = DBSession.query(User.id).filter(User.blocked).all()
        blocked_user_ids = [user_id for (user_id,) in blocked_user_ids]

        blocked_users = get_documents_for_ids(
            blocked_user_ids, None, user_profile_documents_config
        ).get('documents')

        return {'blocked': blocked_users}
