import logging

from c2corg_api import DBSession
from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import user_profile_documents_config
from c2corg_api.views.validation import validate_id, \
    validate_preferred_lang_param
from colander import MappingSchema, SchemaNode, Integer, required
from cornice.resource import resource

log = logging.getLogger(__name__)


class FollowSchema(MappingSchema):
    user_id = SchemaNode(Integer(), missing=required)


def validate_user_id(request):
    """ Check that the user exists.
    """
    user_id = request.validated['user_id']
    user_exists_query = DBSession.query(User). \
        filter(User.id == user_id). \
        exists()
    user_exists = DBSession.query(user_exists_query).scalar()

    if not user_exists:
        request.errors.add(
            'body', 'user_id', 'user {0} does not exist'.format(user_id))


def get_follower_relation(followed_user_id, follower_user_id):
    return DBSession. \
        query(FollowedUser). \
        filter(FollowedUser.followed_user_id == followed_user_id). \
        filter(FollowedUser.follower_user_id == follower_user_id). \
        first()


@resource(path='/users/follow', cors_policy=cors_policy)
class UserFollowRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(schema=FollowSchema(), validators=[validate_user_id])
    def post(self):
        """ Follow the given user.
        Creates a follower relation, so that the authenticated user is
        following the given user.


        Request:
            `POST` `/users/follow`

        Request body:
            {'user_id': @user_id@}

        """
        followed_user_id = self.request.validated['user_id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(
            followed_user_id, follower_user_id)

        if not follower_relation:
            DBSession.add(FollowedUser(
                followed_user_id=followed_user_id,
                follower_user_id=follower_user_id))

        return {}


@resource(path='/users/unfollow', cors_policy=cors_policy)
class UserUnfollowRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(schema=FollowSchema(), validators=[validate_user_id])
    def post(self):
        """ Unfollow the given user.

        Request:
            `POST` `/users/unfollow`

        Request body:
            {'user_id': @user_id@}

        """
        followed_user_id = self.request.validated['user_id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(
            followed_user_id, follower_user_id)

        if follower_relation:
            DBSession.delete(follower_relation)
        else:
            log.warn(
                'tried to delete not existing follower relation '
                '({0}, {1})'.format(followed_user_id, follower_user_id))

        return {}


@resource(path='/users/following-user/{id}', cors_policy=cors_policy)
class UserFollowingUserRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(validators=[validate_id])
    def get(self):
        """ Check if the authenticated user follows the given user.

        Request:
            `GET` `users/following-user/{user_id}`

        Example response:

            {'is_following': true}

        """
        followed_user_id = self.request.validated['id']
        follower_user_id = self.request.authenticated_userid
        follower_relation = get_follower_relation(
            followed_user_id, follower_user_id)

        return {
            'is_following': follower_relation is not None
        }


@resource(path='/users/following', cors_policy=cors_policy)
class UserFollowingRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(validators=[validate_preferred_lang_param])
    def get(self):
        """ Get the users that the authenticated user is following.

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

        followed_user_ids = DBSession. \
            query(FollowedUser.followed_user_id). \
            filter(FollowedUser.follower_user_id == follower_user_id). \
            all()
        followed_user_ids = [user_id for (user_id, ) in followed_user_ids]

        followed_users = get_documents_for_ids(
            followed_user_ids, None, user_profile_documents_config). \
            get('documents')

        return {
            'following': followed_users
        }
