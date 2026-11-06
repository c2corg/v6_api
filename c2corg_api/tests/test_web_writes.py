from dataclasses import dataclass
from typing import Annotated
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, Request

from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers
from c2corg_api.views.resource import Errors
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.handlers import serve_write

PATH = '/test-write'


def _rename_user(request):
    """Rename the user, then answer as the request asks."""
    user = DBSession.get(User, request.authenticated_userid)
    user.name = 'renamed'
    DBSession.flush()
    outcome = request.json.get('outcome')
    if outcome == 'refused by the view':
        # as some views (e.g. a failed login): an error, nothing raised
        request.errors.add('body', 'outcome', 'refused by the view')
        request.errors.status = 401
        return None
    if outcome == 'client address':
        return {'client_addr': request.client_addr}
    if outcome == 'http_error':
        raise HTTPBadRequest('refused by the view')
    if outcome == 'bug':
        raise RuntimeError('boom')
    return {'name': user.name}


def _require_outcome(request, **kwargs):
    outcome = request.json.get('outcome')
    if outcome == 'invalid':
        request.errors.add('body', 'outcome', 'invalid outcome')
    elif outcome == 'not yours':
        # as some validators: the errors of Cornice, and another status
        errors = Errors()
        errors.add('body', 'outcome', 'not yours')
        request.errors.extend(errors)
        request.errors.status = 403


@dataclass
class Env:
    """The application with the test route, the contributor and the rate limit."""

    fastapi_app: FastAPI
    user: User
    name: str
    limit: int


@pytest.fixture(autouse=True)
def env(client, session, settings, user_ids):
    """Add the test route to the application, for every test of the module."""
    fastapi_app = client.app

    async def endpoint(
        request: Request,
        user: Annotated[CurrentUser | None, Depends(current_user)],
    ):
        return await serve_write(
            request,
            user,
            [_require_outcome],
            _rename_user,
            permission='authenticated',
            content_types=['application/json'],
        )

    fastapi_app.add_api_route(PATH, endpoint, methods=['POST'])
    user = session.get(User, user_ids['contributor'])
    name = user.name
    limit = int(settings['rate_limiting.limit'])
    yield Env(fastapi_app=fastapi_app, user=user, name=name, limit=limit)
    DBSession.remove()
    fastapi_app.router.routes[:] = [
        r for r in fastapi_app.router.routes if getattr(r, 'path', '') != PATH
    ]


def post(client, body, status, user='contributor', **kwargs):
    headers = auth_headers(username=user) if user else {}
    headers.update(kwargs.pop('headers', {}))
    return client.post_json(PATH, body, headers=headers, status=status, **kwargs)


def refreshed(session, user_ids):
    session.expire_all()
    return session.get(User, user_ids['contributor'])


def test_answer_is_committed(client, session, user_ids, env):
    assert post(client, {}, 200).json == {'name': 'renamed'}
    user = refreshed(session, user_ids)
    assert user.name == 'renamed'
    assert user.ratelimit_remaining == env.limit - 1


def test_http_error_of_the_view_is_rolled_back(client, session, user_ids, env):
    response = post(client, {'outcome': 'http_error'}, 400)
    assert response.json['errors'] == [
        {
            'location': 'body',
            'name': 'Bad Request',
            'description': 'refused by the view',
        }
    ]
    user = refreshed(session, user_ids)
    # the rate limiting counter too, as with pyramid_tm
    assert user.name == env.name
    assert user.ratelimit_remaining is None


def test_bug_of_the_view_is_rolled_back(client, session, user_ids, env):
    response = post(client, {'outcome': 'bug'}, 500)
    assert response.json['errors'][0]['name'] == 'unexpected error'
    assert refreshed(session, user_ids).name == env.name


def test_validation_errors_are_committed(client, session, user_ids, env):
    response = post(client, {'outcome': 'invalid'}, 400)
    assert response.json['errors'] == [
        {'location': 'body', 'name': 'outcome', 'description': 'invalid outcome'}
    ]
    user = refreshed(session, user_ids)
    # the view did not run, the rate limiting counted the request
    assert user.name == env.name
    assert user.ratelimit_remaining == env.limit - 1


def test_errors_of_the_validators_and_their_status(client):
    response = post(client, {'outcome': 'not yours'}, 403)
    assert response.json['errors'] == [
        {'location': 'body', 'name': 'outcome', 'description': 'not yours'}
    ]


def test_errors_added_by_the_view(client, session, user_ids):
    # as Cornice: they are the answer, and they are committed
    response = post(client, {'outcome': 'refused by the view'}, 401)
    assert response.json['errors'] == [
        {
            'location': 'body',
            'name': 'outcome',
            'description': 'refused by the view',
        }
    ]
    user = refreshed(session, user_ids)
    assert user.name == 'renamed'


def test_client_address(client):
    # as WebOb: the first address of X-Forwarded-For
    response = post(
        client,
        {'outcome': 'client address'},
        200,
        headers={'X-Forwarded-For': '203.0.113.7, 10.0.0.1'},
    )
    assert response.json == {'client_addr': '203.0.113.7'}


def test_invalid_json_body(client):
    headers = auth_headers(username='contributor')
    headers['Content-Type'] = 'application/json'
    response = client.post(PATH, '{not json', headers=headers, status=422)
    [error] = response.json['detail']
    assert error['type'] == 'json_invalid'


def test_content_type_and_permission(client):
    headers = auth_headers(username='contributor')
    headers['Content-Type'] = 'text/plain'
    response = client.post(PATH, '{}', headers=headers, status=415)
    assert response.json['errors'][0]['name'] == 'Content-Type'
    response = post(client, {}, 403, user=None)
    assert response.json['errors'][0]['description'] == 'Authentication required'


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_rate_limit_is_checked_first_and_committed(
    _send_email, client, session, user_ids, env
):
    for _ in range(env.limit):
        post(client, {}, 200)
    # over the limit: a 429 before the content type and the permission
    headers = auth_headers(username='contributor')
    headers['Content-Type'] = 'text/plain'
    response = client.post(PATH, '{}', headers=headers, status=429)
    assert response.json['errors'][0]['description'] == 'Rate limit reached'
    user = refreshed(session, user_ids)
    assert user.ratelimit_remaining == 0
    # the 429 is committed: the window counts as rate limited
    assert user.ratelimit_times == 1
    _send_email.assert_called_once()
