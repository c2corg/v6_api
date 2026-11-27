from dataclasses import dataclass

import pytest

from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers, get_error, send_json
from c2corg_api.views.user_follow import get_follower_relation


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    contributor: User
    contributor2: User
    moderator: User


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor = session.get(User, user_ids['contributor'])
    contributor2 = session.get(User, user_ids['contributor2'])
    moderator = session.get(User, user_ids['moderator'])

    session.add(
        FollowedUser(
            followed_user_id=contributor2.id,
            follower_user_id=contributor.id,
        )
    )

    session.flush()
    return Docs(contributor=contributor, contributor2=contributor2, moderator=moderator)


def is_following(followed_user_id, follower_user_id):
    return get_follower_relation(followed_user_id, follower_user_id) is not None


class TestUserFollowRest:
    PREFIX = '/users/follow'

    def test_follow_unauthenticated(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

    def test_follow(self, client, docs):
        request_body = {'user_id': docs.moderator.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_following(docs.moderator.id, docs.contributor.id)

    def test_follow_already_followed_user(self, client, docs):
        """Test that following an already followed user does not raise an
        error.
        """
        request_body = {'user_id': docs.contributor2.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_following(docs.contributor2.id, docs.contributor.id)

    def test_follow_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserUnfollowRest:
    PREFIX = '/users/unfollow'

    def test_follow_unauthenticated(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

    def test_unfollow(self, client, docs):
        request_body = {'user_id': docs.contributor2.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert not is_following(docs.moderator.id, docs.contributor.id)

    def test_unfollow_not_followed_user(self, client, docs):
        """Test that unfollowing a not followed user does not raise an error."""
        request_body = {'user_id': docs.moderator.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert not is_following(docs.moderator.id, docs.contributor.id)

    def test_follow_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserFollowingUserRest:
    PREFIX = '/users/following-user'

    def test_follow_unauthenticated(self, client):
        client.get(self.PREFIX + '/123', status=403)

    def test_following(self, client, docs):
        headers = auth_headers(username='contributor')
        response = client.get(
            self.PREFIX + f'/{docs.contributor2.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['is_following']

    def test_following_not(self, client, docs):
        headers = auth_headers(username='contributor')
        response = client.get(
            self.PREFIX + f'/{docs.moderator.id}', status=200, headers=headers
        )
        body = response.json

        assert not body['is_following']

    def test_following_invalid_user_id(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(
            self.PREFIX + '/invalid-user-id', status=404, headers=headers
        )

        # an id that is not a number: not found
        body = response.json
        assert body.get('status') == 'error'
        assert body['errors'][0]['name'] == 'Not Found'

    def test_following_wrong_user_id(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(self.PREFIX + '/9999999999', status=200, headers=headers)
        body = response.json

        assert not body['is_following']


class TestUserFollowingRest:
    PREFIX = '/users/following'

    def test_follow_unauthenticated(self, client):
        client.get(self.PREFIX, status=403)

    def test_following(self, client, docs):
        headers = auth_headers(username='contributor')
        response = client.get(self.PREFIX, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        assert 1 == len(following_users)
        assert docs.contributor2.id == following_users[0]['document_id']

    def test_following_empty(self, client):
        headers = auth_headers(username='contributor2')
        response = client.get(self.PREFIX, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        assert 0 == len(following_users)
