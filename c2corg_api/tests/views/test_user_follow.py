from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.user_follow import get_follower_relation


class BaseFollowTest(BaseTestRest):

    def setUp(self):  # noqa
        super(BaseFollowTest, self).setUp()

        self.contributor = self.session.query(User).get(
            self.global_userids['contributor'])
        self.contributor2 = self.session.query(User).get(
            self.global_userids['contributor2'])
        self.moderator = self.session.query(User).get(
            self.global_userids['moderator'])

        self.session.add(FollowedUser(
            followed_user_id=self.contributor2.id,
            follower_user_id=self.contributor.id))

        self.session.flush()

    def is_following(self, followed_user_id, follower_user_id):
        return get_follower_relation(
            followed_user_id, follower_user_id) is not None


class TestUserFollowRest(BaseFollowTest):

    def setUp(self):  # noqa
        super(TestUserFollowRest, self).setUp()
        self._prefix = '/users/follow'

    def test_follow_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_follow(self):
        request_body = {
            'user_id': self.moderator.id
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        self.assertTrue(
            self.is_following(self.moderator.id, self.contributor.id))

    def test_follow_already_followed_user(self):
        """ Test that following an already followed user does not raise an
        error.
        """
        request_body = {
            'user_id': self.contributor2.id
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        self.assertTrue(
            self.is_following(self.contributor2.id, self.contributor.id))

    def test_follow_invalid_user_id(self):
        request_body = {
            'user_id': -1
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertIsNotNone(self.get_error(errors, 'user_id'))


class TestUserUnfollowRest(BaseFollowTest):

    def setUp(self):  # noqa
        super(TestUserUnfollowRest, self).setUp()
        self._prefix = '/users/unfollow'

    def test_follow_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_unfollow(self):
        request_body = {
            'user_id': self.contributor2.id
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        self.assertFalse(
            self.is_following(self.moderator.id, self.contributor.id))

    def test_unfollow_not_followed_user(self):
        """ Test that unfollowing a not followed user does not raise an error.
        """
        request_body = {
            'user_id': self.moderator.id
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        self.assertFalse(
            self.is_following(self.moderator.id, self.contributor.id))

    def test_follow_invalid_user_id(self):
        request_body = {
            'user_id': -1
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertIsNotNone(self.get_error(errors, 'user_id'))


class TestUserFollowingUserRest(BaseFollowTest):

    def setUp(self):  # noqa
        super(TestUserFollowingUserRest, self).setUp()
        self._prefix = '/users/following-user'

    def test_follow_unauthenticated(self):
        self.app.get(self._prefix + '/123', status=403)

    def test_following(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            self._prefix + '/{}'.format(self.contributor2.id),
            status=200, headers=headers)
        body = response.json

        self.assertTrue(body['is_following'])

    def test_following_not(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            self._prefix + '/{}'.format(self.moderator.id),
            status=200, headers=headers)
        body = response.json

        self.assertFalse(body['is_following'])

    def test_following_invalid_user_id(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            self._prefix + '/invalid-user-id',
            status=400, headers=headers)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertIsNotNone(self.get_error(errors, 'id'))

    def test_following_wrong_user_id(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            self._prefix + '/9999999999',
            status=200, headers=headers)
        body = response.json

        self.assertFalse(body['is_following'])


class TestUserFollowingRest(BaseFollowTest):

    def setUp(self):  # noqa
        super(TestUserFollowingRest, self).setUp()
        self._prefix = '/users/following'

    def test_follow_unauthenticated(self):
        self.app.get(self._prefix, status=403)

    def test_following(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(self._prefix, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        self.assertEqual(1, len(following_users))
        self.assertEqual(
            self.contributor2.id, following_users[0]['document_id'])

    def test_following_empty(self):
        headers = self.add_authorization_header(username='contributor2')
        response = self.app.get(self._prefix, status=200, headers=headers)
        body = response.json

        following_users = body['following']
        self.assertEqual(0, len(following_users))
