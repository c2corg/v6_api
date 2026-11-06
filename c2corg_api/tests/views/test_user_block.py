from unittest.mock import MagicMock, Mock

import pytest

from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.tests import assert_errors_contain, auth_headers, get_error, send_json


class BaseBlockTest:
    @pytest.fixture(autouse=True)
    def _setup_base_block_test(self, client, session, settings, user_ids):
        # the Discourse client is global: restore it after the test, or the
        # mock leaks into the tests that run after this one
        self.original_discourse_client = get_discourse_client(settings)

        self.contributor = session.get(User, user_ids['contributor'])
        self.contributor2 = session.get(User, user_ids['contributor2'])
        self.moderator = session.get(User, user_ids['moderator'])

        self.contributor2.blocked = True
        self.contributor2.ratelimit_times = 2

        session.flush()
        self.set_discourse_up()
        yield
        self.set_discourse_not_mocked()

    def set_discourse_client_mock(self, client):
        self.discourse_client = client
        set_discourse_client(client)

    def set_discourse_not_mocked(self):
        self.set_discourse_client_mock(self.original_discourse_client)

    def set_discourse_up(self):
        mock = Mock()
        mock.get_userid = MagicMock()
        mock.suspend = MagicMock()
        mock.unsuspend = MagicMock()
        self.set_discourse_client_mock(mock)

    def set_discourse_down(self, settings):
        mock = APIDiscourseClient(settings)
        mock.get_userid = MagicMock(side_effect=Exception)
        self.set_discourse_client_mock(mock)

    def is_blocked(self, session, user_id):
        user = session.get(User, user_id)
        session.refresh(user)
        return user.blocked


class TestUserBlockRest(BaseBlockTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_block_rest(self, client, _setup_base_block_test):
        self._prefix = '/users/block'

    def test_block_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_block(self, client, session):
        request_body = {'user_id': self.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_blocked(session, self.contributor.id)

    def test_block_already_blocked_user(self, client, session):
        """Test that blocking an already blocked user does not raise an
        error.
        """
        request_body = {'user_id': self.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_blocked(session, self.contributor.id)

    def test_block_discourse_error(self, client, session, settings):
        self.set_discourse_down(settings)

        request_body = {'user_id': self.contributor.id}

        headers = auth_headers(username='moderator')
        body = send_json(
            client, 'post', self._prefix, request_body, status=500, headers=headers
        )
        assert_errors_contain(body.json, 'Internal Server Error')

        assert not self.is_blocked(session, self.contributor.id)

    def test_block_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None


class TestUserUnblockRest(BaseBlockTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_unblock_rest(self, client, _setup_base_block_test):
        self._prefix = '/users/unblock'

    def test_block_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_unblock(self, client, session):
        request_body = {'user_id': self.contributor2.id}
        assert self.is_blocked(session, self.contributor2.id)
        assert self.contributor2.ratelimit_times != 0

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )
        assert not self.is_blocked(session, self.contributor2.id)
        assert self.contributor2.ratelimit_times == 0

    def test_unblock_not_blocked_user(self, client, session):
        """Test that unblocking a not blocked user does not raise an error."""
        request_body = {'user_id': self.contributor.id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert not self.is_blocked(session, self.contributor.id)

    def test_unblock_invalid_user_id(self, client):
        request_body = {'user_id': -1}

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert get_error(errors, 'user_id') is not None

    def test_unblock_discourse_error(self, client, session, settings):
        self.set_discourse_down(settings)

        request_body = {'user_id': self.contributor2.id}
        assert self.is_blocked(session, self.contributor2.id)

        headers = auth_headers(username='moderator')
        body = send_json(
            client, 'post', self._prefix, request_body, status=500, headers=headers
        )
        assert_errors_contain(body.json, 'Internal Server Error')

        assert self.is_blocked(session, self.contributor2.id)


class TestUserBlockedRest(BaseBlockTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_blocked_rest(self, client, _setup_base_block_test):
        self._prefix = '/users/blocked'

    def test_blocked_unauthorized(self, client):
        client.get(self._prefix + '/123', status=403)

        headers = auth_headers(username='contributor')
        client.get(self._prefix, headers=headers, status=403)

    def test_blocked(self, client):
        headers = auth_headers(username='moderator')
        response = client.get(
            self._prefix + f'/{self.contributor2.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['blocked']

    def test_blocked_not(self, client):
        headers = auth_headers(username='moderator')
        response = client.get(
            self._prefix + f'/{self.contributor.id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert not body['blocked']

    def test_blocked_invalid_user_id(self, client):
        headers = auth_headers(username='moderator')
        response = client.get(
            self._prefix + '/invalid-user-id', status=404, headers=headers
        )

        # an id that is not a number: not found
        body = response.json
        assert body.get('status') == 'error'
        assert body['errors'][0]['name'] == 'Not Found'

    def test_blocked_wrong_user_id(self, client):
        headers = auth_headers(username='moderator')
        client.get(self._prefix + '/9999999999', status=400, headers=headers)


class TestUserBlockedAllRest(BaseBlockTest):
    @pytest.fixture(autouse=True)
    def _setup_test_user_blocked_all_rest(self, client, _setup_base_block_test):
        self._prefix = '/users/blocked'

    def test_blocked_unauthenticated(self, client):
        client.get(self._prefix, status=403)

        headers = auth_headers(username='contributor')
        client.get(self._prefix, headers=headers, status=403)

    def test_blocked(self, client):
        headers = auth_headers(username='moderator')
        response = client.get(self._prefix, status=200, headers=headers)
        body = response.json

        blocked_users = body['blocked']
        assert 1 == len(blocked_users)
        assert self.contributor2.id == blocked_users[0]['document_id']
