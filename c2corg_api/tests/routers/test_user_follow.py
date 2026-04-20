"""
Tests for the FastAPI User Follow router (``/v2/users/follow``).

Mirrors ``c2corg_api/tests/views/test_user_follow.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.feed import FollowedUser
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class BaseFollowTestRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        self.contributor = self.session.get(User, global_userids['contributor'])
        self.contributor2 = self.session.get(User, global_userids['contributor2'])
        self.moderator = self.session.get(User, global_userids['moderator'])

        self.session.add(
            FollowedUser(
                followed_user_id=self.contributor2.id,
                follower_user_id=self.contributor.id,
            )
        )
        self.session.flush()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def is_following(self, followed_user_id, follower_user_id):
        return (
            self.session.query(FollowedUser)
            .filter(FollowedUser.followed_user_id == followed_user_id)
            .filter(FollowedUser.follower_user_id == follower_user_id)
            .first()
        ) is not None


class TestUserFollowRouter(BaseFollowTestRouter):
    def test_follow_unauthenticated(self):
        r = self.client.post('/v2/users/follow', json={})
        assert r.status_code == 403

    def test_follow(self):
        body = {'user_id': self.moderator.id}
        r = self.client.post(
            '/v2/users/follow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        assert self.is_following(self.moderator.id, self.contributor.id)

    def test_follow_already_followed_user(self):
        body = {'user_id': self.contributor2.id}
        r = self.client.post(
            '/v2/users/follow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        assert self.is_following(self.contributor2.id, self.contributor.id)

    def test_follow_invalid_user_id(self):
        body = {'user_id': -1}
        r = self.client.post(
            '/v2/users/follow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('user_id' in e.get('name', '') for e in errors)


class TestUserUnfollowRouter(BaseFollowTestRouter):
    def test_unfollow_unauthenticated(self):
        r = self.client.post('/v2/users/unfollow', json={})
        assert r.status_code == 403

    def test_unfollow(self):
        body = {'user_id': self.contributor2.id}
        r = self.client.post(
            '/v2/users/unfollow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        assert not self.is_following(self.moderator.id, self.contributor.id)

    def test_unfollow_not_followed_user(self):
        body = {'user_id': self.moderator.id}
        r = self.client.post(
            '/v2/users/unfollow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        assert not self.is_following(self.moderator.id, self.contributor.id)

    def test_unfollow_invalid_user_id(self):
        body = {'user_id': -1}
        r = self.client.post(
            '/v2/users/unfollow', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        data = r.json()
        errors = data['errors']
        assert any('user_id' in e.get('name', '') for e in errors)


class TestUserFollowingUserRouter(BaseFollowTestRouter):
    def test_follow_unauthenticated(self):
        r = self.client.get('/v2/users/following-user/123')
        assert r.status_code == 403

    def test_following(self):
        r = self.client.get(
            '/v2/users/following-user/{}'.format(self.contributor2.id),
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200
        assert r.json()['is_following']

    def test_following_not(self):
        r = self.client.get(
            '/v2/users/following-user/{}'.format(self.moderator.id),
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200
        assert not r.json()['is_following']

    def test_following_wrong_user_id(self):
        r = self.client.get(
            '/v2/users/following-user/9999999999',
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200
        assert not r.json()['is_following']

    def test_following_invalid_user_id(self):
        # Non-integer path param; FastAPI returns 422 (Pyramid returned 400)
        r = self.client.get(
            '/v2/users/following-user/invalid-user-id',
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code in (400, 422)


class TestUserFollowingRouter(BaseFollowTestRouter):
    def test_follow_unauthenticated(self):
        r = self.client.get('/v2/users/following')
        assert r.status_code == 403

    def test_following(self):
        r = self.client.get(
            '/v2/users/following', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()
        following_users = body['following']
        assert 1 == len(following_users)
        assert self.contributor2.id == following_users[0]['document_id']

    def test_following_empty(self):
        r = self.client.get(
            '/v2/users/following', headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 200
        body = r.json()
        assert 0 == len(body['following'])
