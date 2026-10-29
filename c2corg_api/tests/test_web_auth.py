"""current_user() accepts and rejects the same tokens as the view routes."""

import datetime
from typing import Annotated

import pytest
from fastapi import Depends

from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.web.auth import CurrentUser, current_user

PROBE = '/test/whoami'


def whoami(user: Annotated[CurrentUser | None, Depends(current_user)]):
    return {'user': None if user is None else [user.id, user.is_moderator]}


class TestAuthParity(BaseTestRest):
    def setUp(self):
        fastapi_app = self.app.app.fastapi_app
        if not any(
            getattr(r, 'path', None) == PROBE for r in fastapi_app.router.routes
        ):
            fastapi_app.add_api_route(PROBE, whoami, methods=['GET'])
        self.contributor = self.global_userids['contributor']
        self.moderator = self.global_userids['moderator']

    def _add_token(self, value, user_id, expire):
        self.session.add(Token(value=value, userid=user_id, expire=expire))
        self.session.flush()

    def headers_cases(self):
        """Return (name, Authorization header or None) for every case."""
        token = self.global_tokens['contributor']
        moderator_token = self.global_tokens['moderator']
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        # a token string the database knows but that is not a valid JWT
        self._add_token('known-but-not-a-jwt', self.contributor, future)
        self._add_token('expired-in-db', self.contributor, past)
        return [
            ('none', None),
            ('contributor', f'JWT token="{token}"'),
            ('contributor, bare token', f'JWT {token}'),
            ('moderator', f'JWT token="{moderator_token}"'),
            ('another scheme', f'Bearer {token}'),
            ('unknown token', 'JWT token="not-a-token"'),
            ('expired in the database', 'JWT token="expired-in-db"'),
            ('known but not a JWT', 'JWT token="known-but-not-a-jwt"'),
            ('empty', 'JWT'),
            ('garbage', 'garbage'),
        ]

    def answers(self, header):
        headers = {} if header is None else {'Authorization': header}
        view_user = self.app.get('/users/account', headers=headers, status='*')
        view_moderator = self.app.get('/users/blocked', headers=headers, status='*')
        fastapi = self.app.get(PROBE, headers=headers, status='*')
        return view_user, view_moderator, fastapi

    def test_same_answers(self):
        for name, header in self.headers_cases():
            view_user, view_moderator, fastapi = self.answers(header)
            if view_user.status_int in (401, 403) and 'errors' in view_user.json:
                rejected = view_user.json['errors'][0]['description']
            else:
                rejected = None
            if rejected in ('Invalid token', 'account blocked'):
                # refused before any view, on both sides
                assert fastapi.status_int == view_user.status_int, name
                assert fastapi.json['errors'] == view_user.json['errors'], name
                continue
            assert fastapi.status_int == 200, name
            user = fastapi.json['user']
            if view_user.status_int == 200:
                assert user is not None, name
                assert user[0] == self.user_of(view_user), name
                assert user[1] == (view_moderator.status_int == 200), name
            else:
                assert user is None, name

    def user_of(self, account_response):
        email = account_response.json['email']
        return self.session.query(User.id).filter(User.email == email).scalar()

    def test_blocked_user(self):
        user = self.session.get(User, self.contributor)
        user.blocked = True
        self.session.flush()
        header = f'JWT token="{self.global_tokens["contributor"]}"'
        view_user, _, fastapi = self.answers(header)
        assert view_user.status_int == fastapi.status_int == 403
        assert fastapi.json['errors'] == view_user.json['errors']

    @pytest.mark.parametrize('header', [None, 'JWT token="not-a-token"'])
    def test_errors_keep_cors_headers(self, header):
        headers = {'Origin': self.settings['cors.allowed_origins'].split()[0]}
        if header:
            headers['Authorization'] = header
        response = self.app.get(PROBE, headers=headers, status='*')
        assert response.headers['Access-Control-Allow-Origin'] == headers['Origin']
