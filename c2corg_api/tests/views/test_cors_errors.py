import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers

WAYPOINT = {
    'waypoint_type': 'summit',
    'elevation': 3779,
    'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
    'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
}


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    origin: object


@pytest.fixture(autouse=True)
def docs(settings) -> Docs:
    origin = settings['cors.allowed_origins'].split()[0]
    return Docs(origin=origin)


def assert_cors(response, origin):
    assert response.headers['Access-Control-Allow-Origin'] == origin
    assert response.headers['Access-Control-Expose-Headers'] == 'Content-Type'


def test_invalid_token(client, docs):
    # 401 from the token validation (web.auth)
    response = client.post_json(
        '/waypoints',
        WAYPOINT,
        headers={'Authorization': 'JWT token="not-a-token"', 'Origin': docs.origin},
        status=401,
    )
    assert_cors(response, docs.origin)


def test_rate_limited(client, session, user_ids, docs):
    # 429 from the rate limiting
    user = session.get(User, user_ids['contributor'])
    user.ratelimit_reset = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        minutes=5
    )
    user.ratelimit_remaining = 0
    session.flush()
    headers = auth_headers(username='contributor')
    headers['Origin'] = docs.origin
    with patch('c2corg_api.emails.email_service.EmailService._send_email'):
        response = client.post_json('/waypoints', WAYPOINT, headers=headers, status=429)
    assert_cors(response, docs.origin)


def test_unexpected_error(client, docs):
    # 500 of an unexpected error (UnexpectedErrorMiddleware of FastAPI,
    # as the catch-all error view of Pyramid did)
    with patch('c2corg_api.views.user.try_login', side_effect=RuntimeError('boom')):
        # a dummy password: try_login fails before checking it
        body = {'username': 'contributor', 'password': 'not checked'}  # nosec B105
        response = client.post_json(
            '/users/login',
            body,
            headers={'Origin': docs.origin},
            status=500,
        )
    assert_cors(response, docs.origin)


def test_unknown_route(client, docs):
    # 404 answered by Pyramid itself, not by a Cornice view
    response = client.get('/no-such-route', headers={'Origin': docs.origin}, status=404)
    assert_cors(response, docs.origin)


def test_only_for_allowed_origins(client):
    response = client.post_json(
        '/waypoints',
        WAYPOINT,
        headers={
            'Authorization': 'JWT token="not-a-token"',
            'Origin': 'https://evil.example.org',
        },
        status=401,
    )
    assert 'Access-Control-Allow-Origin' not in response.headers


def test_without_origin(client):
    response = client.post_json(
        '/waypoints',
        WAYPOINT,
        headers={'Authorization': 'JWT token="not-a-token"'},
        status=401,
    )
    assert 'Access-Control-Allow-Origin' not in response.headers
