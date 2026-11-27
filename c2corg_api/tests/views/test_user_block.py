from dataclasses import dataclass
from unittest.mock import MagicMock, Mock

import pytest

from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.tests import assert_errors_contain, auth_headers, get_error, send_json


@pytest.fixture(autouse=True)
def discourse(settings):
    """Mock the Discourse client; restore the real one after the test."""
    # the Discourse client is global: without the restore, the mock leaks
    # into the tests that run after this one
    original = get_discourse_client(settings)
    mock = Mock()
    mock.get_userid = MagicMock()
    mock.suspend = MagicMock()
    mock.unsuspend = MagicMock()
    set_discourse_client(mock)
    yield mock
    set_discourse_client(original)


def set_discourse_down(settings):
    mock = APIDiscourseClient(settings)
    mock.get_userid = MagicMock(side_effect=Exception)
    set_discourse_client(mock)


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

    contributor2.blocked = True
    contributor2.ratelimit_times = 2

    session.flush()
    return Docs(contributor=contributor, contributor2=contributor2, moderator=moderator)


def is_blocked(session, user_id):
    user = session.get(User, user_id)
    session.refresh(user)
    return user.blocked


class TestUserBlockRest:
    PREFIX = '/users/block'

    def test_block_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_block(self, client, session, docs):
        request_body = {'user_id': docs.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_blocked(session, docs.contributor.id)

    def test_block_already_blocked_user(self, client, session, docs):
        """Test that blocking an already blocked user does not raise an
        error.
        """
        request_body = {'user_id': docs.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_blocked(session, docs.contributor.id)

    def test_block_discourse_error(self, client, session, settings, docs):
        set_discourse_down(settings)

        request_body = {'user_id': docs.contributor.id}

        headers = auth_headers(username='moderator')
        body = send_json(
            client, 'post', self.PREFIX, request_body, status=500, headers=headers
        )
        assert_errors_contain(body.json, 'Internal Server Error')

        assert not is_blocked(session, docs.contributor.id)

    def test_block_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserUnblockRest:
    PREFIX = '/users/unblock'

    def test_block_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_unblock(self, client, session, docs):
        request_body = {'user_id': docs.contributor2.id}
        assert is_blocked(session, docs.contributor2.id)
        assert docs.contributor2.ratelimit_times != 0

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )
        assert not is_blocked(session, docs.contributor2.id)
        assert docs.contributor2.ratelimit_times == 0

    def test_unblock_not_blocked_user(self, client, session, docs):
        """Test that unblocking a not blocked user does not raise an error."""
        request_body = {'user_id': docs.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert not is_blocked(session, docs.contributor.id)

    def test_unblock_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None

    def test_unblock_discourse_error(self, client, session, settings, docs):
        set_discourse_down(settings)

        request_body = {'user_id': docs.contributor2.id}
        assert is_blocked(session, docs.contributor2.id)

        headers = auth_headers(username='moderator')
        body = send_json(
            client, 'post', self.PREFIX, request_body, status=500, headers=headers
        )
        assert_errors_contain(body.json, 'Internal Server Error')

        assert is_blocked(session, docs.contributor2.id)


class TestUserBlockedRest:
    PREFIX = '/users/blocked'

    def test_blocked_unauthorized(self, client):
        client.get(self.PREFIX + '/123', status=403)

        headers = auth_headers(username='contributor')
        client.get(self.PREFIX, headers=headers, status=403)

    def test_blocked(self, client, docs):
        headers = auth_headers(username='moderator')
        response = client.get(
            self.PREFIX + f'/{docs.contributor2.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['blocked']

    def test_blocked_not(self, client, docs):
        headers = auth_headers(username='moderator')
        response = client.get(
            self.PREFIX + f'/{docs.contributor.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert not body['blocked']

    def test_blocked_invalid_user_id(self, client):
        headers = auth_headers(username='moderator')
        response = client.get(
            self.PREFIX + '/invalid-user-id', status=404, headers=headers
        )

        # an id that is not a number: not found
        body = response.json
        assert body.get('status') == 'error'
        assert body['errors'][0]['name'] == 'Not Found'

    def test_blocked_wrong_user_id(self, client):
        headers = auth_headers(username='moderator')
        client.get(self.PREFIX + '/9999999999', status=400, headers=headers)


class TestUserBlockedAllRest:
    PREFIX = '/users/blocked'

    def test_blocked_unauthenticated(self, client):
        client.get(self.PREFIX, status=403)

        headers = auth_headers(username='contributor')
        client.get(self.PREFIX, headers=headers, status=403)

    def test_blocked(self, client, docs):
        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX, status=200, headers=headers)
        body = response.json

        blocked_users = body['blocked']
        assert 1 == len(blocked_users)
        assert docs.contributor2.id == blocked_users[0]['document_id']
