import pytest

from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers, get_error, send_json
from c2corg_api.views.user_follow import get_follower_relation


class BaseFollowTest:
    @pytest.fixture(autouse=True)
    def _setup_base_follow_test(self, client, session, user_ids):

        self.contributor = session.get(User, user_ids['contributor'])
        self.contributor2 = session.get(User, user_ids['contributor2'])
        self.moderator = session.get(User, user_ids['moderator'])

        session.add(
            FollowedUser(
                followed_user_id=self.contributor2.id,
                follower_user_id=self.contributor.id,
            )
        )

        session.flush()

    def is_following(self, followed_user_id, follower_user_id):
        return get_follower_relation(followed_user_id, follower_user_id) is not None


class TestUserFollowRest(BaseFollowTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_follow_rest(self, client, _setup_base_follow_test):
        self._prefix = '/users/follow'

    def test_follow_unauthenticated(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

    def test_follow(self, client):
        request_body = {'user_id': self.moderator.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_following(self.moderator.id, self.contributor.id)

    def test_follow_already_followed_user(self, client):
        """Test that following an already followed user does not raise an
        error.
        """
        request_body = {'user_id': self.contributor2.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_following(self.contributor2.id, self.contributor.id)

    def test_follow_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserUnfollowRest(BaseFollowTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_unfollow_rest(self, client, _setup_base_follow_test):
        self._prefix = '/users/unfollow'

    def test_follow_unauthenticated(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

    def test_unfollow(self, client):
        request_body = {'user_id': self.contributor2.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert not self.is_following(self.moderator.id, self.contributor.id)

    def test_unfollow_not_followed_user(self, client):
        """Test that unfollowing a not followed user does not raise an error."""
        request_body = {'user_id': self.moderator.id}

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert not self.is_following(self.moderator.id, self.contributor.id)

    def test_follow_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserFollowingUserRest(BaseFollowTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_following_user_rest(self, client, _setup_base_follow_test):
        self._prefix = '/users/following-user'

    def test_follow_unauthenticated(self, client):
        client.get(self._prefix + '/123', status=403)

    def test_following(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(
            self._prefix + f'/{self.contributor2.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['is_following']

    def test_following_not(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(
            self._prefix + f'/{self.moderator.id}', status=200, headers=headers
        )
        body = response.json

        assert not body['is_following']

    def test_following_invalid_user_id(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(
            self._prefix + '/invalid-user-id', status=404, headers=headers
        )

        # an id that is not a number: not found
        body = response.json
        assert body.get('status') == 'error'
        assert body['errors'][0]['name'] == 'Not Found'

    def test_following_wrong_user_id(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(self._prefix + '/9999999999', status=200, headers=headers)
        body = response.json

        assert not body['is_following']


class TestUserFollowingRest(BaseFollowTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_following_rest(self, client, _setup_base_follow_test):
        self._prefix = '/users/following'

    def test_follow_unauthenticated(self, client):
        client.get(self._prefix, status=403)

    def test_following(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(self._prefix, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        assert 1 == len(following_users)
        assert self.contributor2.id == following_users[0]['document_id']

    def test_following_empty(self, client):
        headers = auth_headers(username='contributor2')
        response = client.get(self._prefix, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        assert 0 == len(following_users)
