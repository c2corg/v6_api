import datetime
from unittest.mock import Mock

import pytest

from c2corg_api.models.account_removal import AccountRemovalRequest
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import (
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.tests import auth_headers, send_json

TARGET_FORUM_ID = 49513


@pytest.fixture(autouse=True)
def discourse(settings, user_ids):
    """Mock the Discourse client; restore the real one after the test."""
    original = get_discourse_client(settings)
    mock = Mock()
    forum_moderators = {user_ids['contributor'], user_ids['contributor2']}
    mock.is_moderator = Mock(side_effect=lambda user_id: user_id in forum_moderators)
    mock.get_userid = Mock(return_value=1234)
    set_discourse_client(mock)
    yield mock
    set_discourse_client(original)


def future(days=7):
    today = datetime.datetime.now(datetime.UTC).date()
    return (today + datetime.timedelta(days=days)).isoformat()


@pytest.fixture
def second_moderator(session, user_ids):
    """Make the contributor2 a moderator of the topoguide, who is one of the forum."""
    user = session.get(User, user_ids['contributor2'])
    user.moderator = True
    session.flush()
    return user


def body_for(user_id, target_user_id, **kwargs):
    body = {
        'user_id': user_id,
        'reason': 'anonymization',
        'executable_after': future(),
        'target_user_id': target_user_id,
        'target_forum_id': TARGET_FORUM_ID,
    }
    body.update(kwargs)
    return body


class TestCreate:
    PREFIX = '/users/removals'

    def test_unauthorized(self, client, discourse, user_ids):
        # a valid body: it is validated before the role is checked
        body = body_for(user_ids['contributor'], user_ids['contributor2'])
        send_json(client, 'post', self.PREFIX, body, status=403)

        # neither a moderator of the topoguide, nor of the forum
        discourse.is_moderator = Mock(return_value=False)
        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=403)

    def test_create(self, client, session, user_ids):
        headers = auth_headers(username='moderator')
        body = body_for(
            user_ids['contributor'],
            user_ids['contributor2'],
            forum_url='https://forum.camptocamp.org/t/1',
        )
        response = send_json(
            client, 'post', self.PREFIX, body, headers=headers, status=200
        )

        removal = response.json
        assert removal['user_id'] == user_ids['contributor']
        assert removal['forum_id'] == 1234
        assert removal['reason'] == 'anonymization'
        assert removal['executable_after'] == body['executable_after']
        assert removal['target_user_id'] == user_ids['contributor2']
        assert removal['forum_url'] == 'https://forum.camptocamp.org/t/1'
        assert removal['requested_by']['id'] == user_ids['moderator']
        assert removal['topoguide_validated_by'] is None
        assert removal['forum_validated_by'] is None
        assert removal['status'] == 'in_progress'

        saved = session.get(AccountRemovalRequest, removal['id'])
        assert saved.user_name == 'Contributor'

    def test_create_as_forum_moderator(self, client, user_ids):
        # the contributor is a moderator of the forum
        headers = auth_headers(username='contributor')
        body = body_for(user_ids['contributor2'], user_ids['moderator'])
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=200)

    def test_create_twice(self, client, user_ids):
        headers = auth_headers(username='moderator')
        body = body_for(user_ids['contributor'], user_ids['contributor2'])
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=200)
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=409)

    def test_create_invalid(self, client, user_ids):
        headers = auth_headers(username='moderator')
        user_id = user_ids['contributor']

        # into itself
        body = body_for(user_id, user_id)
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

        # unknown users
        body = body_for(-1, user_ids['contributor2'])
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)
        body = body_for(user_id, -1)
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

        # a moderator
        body = body_for(user_ids['moderator'], user_ids['contributor2'])
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

        # in the past
        body = body_for(user_id, user_ids['contributor2'], executable_after=future(-1))
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

        # reason
        body = body_for(user_id, user_ids['contributor2'], reason='because')
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=422)


def create(client, user_ids, **kwargs):
    headers = auth_headers(username='moderator')
    body = body_for(user_ids['contributor'], user_ids['contributor2'], **kwargs)
    response = send_json(client, 'post', '/users/removals', body, headers=headers)
    return response.json['id']


class TestValidate:
    PREFIX = '/users/removals/validate'

    def test_validate_both_sides(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)

        # contributor2 (a moderator of the topoguide) validates the topoguide
        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide'}
        response = send_json(client, 'post', self.PREFIX, body, headers=headers)
        removal = response.json
        assert removal['topoguide_validated_by']['id'] == user_ids['contributor2']
        assert removal['topoguide_validated_at'] is not None
        assert removal['status'] == 'in_progress'

        # contributor (a moderator of the forum) validates the forum
        headers = auth_headers(username='contributor')
        body = {'id': request_id, 'side': 'forum'}
        response = send_json(client, 'post', self.PREFIX, body, headers=headers)
        removal = response.json
        assert removal['forum_validated_by']['id'] == user_ids['contributor']
        assert removal['status'] == 'validated'

    def test_author_cannot_validate(self, client, user_ids):
        request_id = create(client, user_ids)

        headers = auth_headers(username='moderator')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=403)

    def test_not_a_moderator_of_the_side(self, client, user_ids):
        request_id = create(client, user_ids)

        # the contributor is a moderator of the forum, not of the topoguide
        headers = auth_headers(username='contributor')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=403)

    def test_one_side_by_person(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)

        # contributor2 is a moderator of both: he validates only one side
        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers)
        body = {'id': request_id, 'side': 'forum'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=403)

    def test_already_validated(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)

        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers)
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=409)

    def test_done(self, client, session, user_ids, second_moderator):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        removal.done_at = datetime.datetime.now(datetime.UTC)
        session.flush()

        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

    def test_unknown(self, client, second_moderator):
        headers = auth_headers(username='contributor2')
        body = {'id': -1, 'side': 'topoguide'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=404)

    def test_forum_down(self, client, user_ids, discourse, second_moderator):
        request_id = create(client, user_ids)
        discourse.is_moderator = Mock(side_effect=Exception)

        headers = auth_headers(username='contributor')
        body = {'id': request_id, 'side': 'forum'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=503)


class TestUnvalidate:
    PREFIX = '/users/removals/unvalidate'

    def test_unvalidate(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)
        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide'}
        send_json(client, 'post', '/users/removals/validate', body, headers=headers)

        # the discussion is required
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=422)

        body['forum_url'] = 'https://forum.camptocamp.org/t/2'
        response = send_json(client, 'post', self.PREFIX, body, headers=headers)
        removal = response.json
        assert removal['topoguide_validated_by'] is None
        assert removal['forum_url'] == 'https://forum.camptocamp.org/t/2'
        assert removal['status'] == 'in_progress'

    def test_not_validated(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)
        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide', 'forum_url': 'https://f.org/1'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)

    def test_done(self, client, session, user_ids, second_moderator):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        removal.topoguide_validated_by = user_ids['contributor2']
        removal.done_at = datetime.datetime.now(datetime.UTC)
        session.flush()

        headers = auth_headers(username='contributor2')
        body = {'id': request_id, 'side': 'topoguide', 'forum_url': 'https://f.org/1'}
        send_json(client, 'post', self.PREFIX, body, headers=headers, status=400)


class TestUpdateAndCancel:
    def test_update_forum_url(self, client, user_ids):
        request_id = create(client, user_ids)
        headers = auth_headers(username='moderator')
        body = {'id': request_id, 'forum_url': 'https://forum.camptocamp.org/t/3'}
        response = send_json(
            client, 'post', '/users/removals/update', body, headers=headers
        )
        assert response.json['forum_url'] == 'https://forum.camptocamp.org/t/3'

    def test_update_validated(self, client, session, user_ids):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        removal.topoguide_validated_by = user_ids['moderator']
        removal.forum_validated_by = user_ids['contributor']
        session.flush()

        headers = auth_headers(username='moderator')
        body = {'id': request_id, 'forum_url': 'https://forum.camptocamp.org/t/3'}
        send_json(
            client, 'post', '/users/removals/update', body, headers=headers, status=400
        )

    def test_cancel(self, client, session, user_ids):
        request_id = create(client, user_ids)
        headers = auth_headers(username='moderator')
        send_json(
            client,
            'post',
            '/users/removals/cancel',
            {'id': request_id},
            headers=headers,
        )
        assert session.get(AccountRemovalRequest, request_id) is None

        # a new request is possible again
        create(client, user_ids)

    def test_cancel_unauthorized(self, client, user_ids, discourse):
        request_id = create(client, user_ids)
        discourse.is_moderator = Mock(return_value=False)
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'post',
            '/users/removals/cancel',
            {'id': request_id},
            headers=headers,
            status=403,
        )


class TestRead:
    PREFIX = '/users/removals'

    def test_unauthorized(self, client, discourse):
        client.get(self.PREFIX, status=403)

        discourse.is_moderator = Mock(return_value=False)
        headers = auth_headers(username='contributor')
        client.get(self.PREFIX, headers=headers, status=403)

    def test_list(self, client, user_ids):
        request_id = create(client, user_ids)

        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX, headers=headers, status=200)
        assert [r['id'] for r in response.json['removals']] == [request_id]
        removal = response.json['removals'][0]
        assert removal['requested_by'] == {
            'id': user_ids['moderator'],
            'name': 'Moderator',
        }
        assert response.json['roles'] == {'topoguide': True, 'forum': False}

        # a moderator of the forum
        headers = auth_headers(username='contributor')
        response = client.get(self.PREFIX, headers=headers, status=200)
        assert response.json['roles'] == {'topoguide': False, 'forum': True}

    def test_count(self, client, user_ids):
        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json == {'open': 0}

        create(client, user_ids)
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json == {'open': 1}

        # a moderator of the forum only
        headers = auth_headers(username='contributor')
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json == {'open': 1}

        # neither of the topoguide nor of the forum
        headers = auth_headers(username='contributor3')
        client.get(self.PREFIX + '/count', headers=headers, status=403)
