"""current_user() accepts and rejects the same tokens as the view routes."""

import datetime
from typing import Annotated

import jwt
import pytest
from fastapi import Depends

from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.security.roles import create_claims, hash_token
from c2corg_api.web.auth import (
    Authorization,
    CurrentUser,
    current_user,
    parse_authorization,
)

PROBE = '/test/whoami'


def whoami(user: Annotated[CurrentUser | None, Depends(current_user)]):
    return {'user': None if user is None else [user.id, user.is_moderator]}


class TestAuthParity:
    @pytest.fixture(autouse=True)
    def _setup_test_auth_parity(self, client, user_ids):
        fastapi_app = client.app
        if not any(
            getattr(r, 'path', None) == PROBE for r in fastapi_app.router.routes
        ):
            fastapi_app.add_api_route(PROBE, whoami, methods=['GET'])
        self.contributor = user_ids['contributor']
        self.moderator = user_ids['moderator']

    def _add_token(self, session, value, user_id, expire):
        session.add(Token(value=hash_token(value), userid=user_id, expire=expire))
        session.flush()

    def headers_cases(self, session, tokens):
        """Return (name, Authorization header or None) for every case."""
        token = tokens['contributor']
        moderator_token = tokens['moderator']
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        # a token string the database knows but that is not a valid JWT
        self._add_token(session, 'known-but-not-a-jwt', self.contributor, future)
        self._add_token(session, 'expired-in-db', self.contributor, past)
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

    def answers(self, client, header):
        headers = {} if header is None else {'Authorization': header}
        view_user = client.get('/users/account', headers=headers, status='*')
        view_moderator = client.get('/users/blocked', headers=headers, status='*')
        fastapi = client.get(PROBE, headers=headers, status='*')
        return view_user, view_moderator, fastapi

    def test_same_answers(self, client, session, tokens):
        for name, header in self.headers_cases(session, tokens):
            view_user, view_moderator, fastapi = self.answers(client, header)
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
                assert user[0] == self.user_of(session, view_user), name
                assert user[1] == (view_moderator.status_int == 200), name
            else:
                assert user is None, name

    def user_of(self, session, account_response):
        email = account_response.json['email']
        return session.query(User.id).filter(User.email == email).scalar()

    def test_blocked_user(self, client, session, tokens):
        user = session.get(User, self.contributor)
        user.blocked = True
        session.flush()
        header = f'JWT token="{tokens["contributor"]}"'
        view_user, _, fastapi = self.answers(client, header)
        assert view_user.status_int == fastapi.status_int == 403
        assert fastapi.json['errors'] == view_user.json['errors']

    @pytest.mark.parametrize(
        ('issued_in', 'authenticated'),
        [
            (datetime.timedelta(seconds=-10), True),
            # another API server may be a little ahead of this one
            (datetime.timedelta(seconds=30), True),
            (datetime.timedelta(minutes=5), False),
        ],
    )
    def test_issued_at(self, issued_in, authenticated, client, session, settings):
        user = session.get(User, self.contributor)
        now = datetime.datetime.now(datetime.UTC) + issued_in
        exp = now + datetime.timedelta(days=1)
        token = jwt.encode(
            create_claims(user, now, exp),
            settings['jwt.private_key'],
            algorithm='HS256',
        )
        self._add_token(session, token, self.contributor, exp)

        response = client.get(PROBE, headers={'Authorization': f'JWT {token}'})
        expected = [self.contributor, False] if authenticated else None
        assert response.json['user'] == expected

    @pytest.mark.parametrize('header', [None, 'JWT token="not-a-token"'])
    def test_errors_keep_cors_headers(self, header, client, settings):
        headers = {'Origin': settings['cors.allowed_origins'].split()[0]}
        if header:
            headers['Authorization'] = header
        response = client.get(PROBE, headers=headers, status='*')
        assert response.headers['Access-Control-Allow-Origin'] == headers['Origin']


@pytest.mark.parametrize(
    ('header', 'expected'),
    [
        (None, None),
        ('', None),
        ('JWT token="a.b.c"', ('JWT', 'a.b.c')),
        ('JWT a.b.c', ('JWT', 'a.b.c')),
        ('Bearer a.b.c', ('Bearer', 'a.b.c')),
        ('JWT', ('JWT', '')),
        ('JWT token=""', ('JWT', '')),
        # an unterminated quote: the token is what follows it
        ('JWT token="a.b.c', ('JWT', 'a.b.c')),
        ('garbage', ('garbage', '')),
    ],
)
def test_parse_authorization(header, expected):
    authorization = parse_authorization(header)
    assert authorization == expected
    if expected is not None:
        assert isinstance(authorization, Authorization)
