import logging

from c2corg_api import DBSession
from c2corg_api.models.feed import FollowedUser
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import user_profile_documents_config
from c2corg_api.views.resource import resource
from c2corg_api.views.validation import (
    validate_body_user_id,
    validate_id,
    validate_preferred_lang_param,
)

log = logging.getLogger(__name__)


class FollowSchema(Schema):
    user_id: Int


def get_follower_relation(followed_user_id, follower_user_id):
    return (
        DBSession.query(FollowedUser)
        .filter(FollowedUser.followed_user_id == followed_user_id)
        .filter(FollowedUser.follower_user_id == follower_user_id)
        .first()
    )


@resource(path='/users/follow')
class UserFollowRest(ACLDefault):
    @restricted_json_view(
        validators=[body_validator(FollowSchema), validate_body_user_id],
    )
    def post(self):
        """Follow the given user.

        Creates a follower relation, so that the authenticated user is following the
        given user.


        Request:
            `POST` `/users/follow`

        Request body:
            {'user_id': @user_id@}
        """
        followed_user_id = self.request.validated['user_id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(followed_user_id, follower_user_id)

        if not follower_relation:
            DBSession.add(
                FollowedUser(
                    followed_user_id=followed_user_id, follower_user_id=follower_user_id
                )
            )

        return {}


@resource(path='/users/unfollow')
class UserUnfollowRest(ACLDefault):
    @restricted_json_view(
        validators=[body_validator(FollowSchema), validate_body_user_id],
    )
    def post(self):
        """Unfollow the given user.

        Request:
            `POST` `/users/unfollow`

        Request body:
            {'user_id': @user_id@}

        """
        followed_user_id = self.request.validated['user_id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(followed_user_id, follower_user_id)

        if follower_relation:
            DBSession.delete(follower_relation)
        else:
            log.warning(
                f'tried to delete not existing follower relation ({followed_user_id}, '
                f'{follower_user_id})'
            )

        return {}


@resource(path='/users/following-user/{id}')
class UserFollowingUserRest(ACLDefault):
    @restricted_json_view(validators=[validate_id])
    def get(self):
        """Check if the authenticated user follows the given user.

        Request:
            `GET` `users/following-user/{user_id}`

        Example response:

            {'is_following': true}

        """
        followed_user_id = self.request.validated['id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(followed_user_id, follower_user_id)

        return {'is_following': follower_relation is not None}


@resource(path='/users/following')
class UserFollowingRest(ACLDefault):
    @restricted_json_view(validators=[validate_preferred_lang_param])
    def get(self):
        """Get the users that the authenticated user is following.

        Request:
            `GET` `/users/following`

        Example response:

            {
                'following': [
                    {
                        'document_id': 123,
                        ...
                    }
                ]
            }
        """
        follower_user_id = self.request.authenticated_userid

        followed_user_ids = (
            DBSession.query(FollowedUser.followed_user_id)
            .filter(FollowedUser.follower_user_id == follower_user_id)
            .all()
        )
        followed_user_ids = [user_id for (user_id,) in followed_user_ids]

        followed_users = get_documents_for_ids(
            followed_user_ids, None, user_profile_documents_config
        ).get('documents')

        return {'following': followed_users}
