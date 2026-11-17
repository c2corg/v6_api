import datetime
from unittest.mock import Mock

import pytest
from pydiscourse.exceptions import DiscourseClientError

from c2corg_api.models.account_removal import AccountRemovalRequest
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import (
    get_discourse_client,
    set_discourse_client,
)
from c2corg_api.tests import auth_headers, send_json

CLOSED_FORUM_ID = 49513

# The test users: `moderator` is a moderator of the topoguide; contributor2 and
# contributor3 are moderators of the forum (Discourse is mocked); `contributor`
# is the account to remove; contributornotos stands for the closed account.


def forum_id(user_id):
    return 1000 + user_id


def not_found():
    return DiscourseClientError('not found', response=Mock(status_code=404))


@pytest.fixture(autouse=True)
def closed_account(settings, user_ids):
    """The closed account the anonymized accounts go to."""
    closed_id = user_ids['contributornotos']
    settings['users.closed_account_id'] = str(closed_id)
    settings['users.closed_account_forum_id'] = str(CLOSED_FORUM_ID)
    yield closed_id
    del settings['users.closed_account_id']
    del settings['users.closed_account_forum_id']


@pytest.fixture(autouse=True)
def discourse(settings, user_ids):
    """Mock the Discourse client; restore the real one after the test."""
    original = get_discourse_client(settings)
    mock = Mock()
    forum_moderators = {user_ids['contributor2'], user_ids['contributor3']}
    mock.is_moderator = Mock(side_effect=lambda user_id: user_id in forum_moderators)
    mock.get_userid = Mock(side_effect=forum_id)
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


def body_for(user_id, **kwargs):
    body = {
        'user_id': user_id,
        'reason': 'anonymization',
        'user_request_date': future(0),
        'executable_after': future(),
    }
    body.update(kwargs)
    return body


def post(client, url, body, username, status=200):
    headers = auth_headers(username=username)
    return send_json(client, 'post', url, body, headers=headers, status=status)


class TestCreate:
    PREFIX = '/users/removals'

    def test_unauthorized(self, client, user_ids):
        # a valid body: it is validated before the role is checked
        body = body_for(user_ids['contributor'])
        send_json(client, 'post', self.PREFIX, body, status=403)

        # neither a moderator of the topoguide, nor of the forum
        post(client, self.PREFIX, body, 'contributornotos', status=403)

    def test_create(self, client, session, user_ids, closed_account):
        body = body_for(
            user_ids['contributor'], forum_url='https://forum.camptocamp.org/t/1'
        )
        removal = post(client, self.PREFIX, body, 'moderator').json

        assert removal['user_id'] == user_ids['contributor']
        assert removal['forum_id'] == forum_id(user_ids['contributor'])
        assert removal['reason'] == 'anonymization'
        assert removal['executable_after'] == body['executable_after']
        # an anonymization goes to the closed account
        assert removal['target_user_id'] == closed_account
        assert removal['target_forum_id'] == CLOSED_FORUM_ID
        assert removal['forum_url'] == 'https://forum.camptocamp.org/t/1'
        assert removal['requested_by']['id'] == user_ids['moderator']
        assert removal['topoguide_validated_by'] is None
        assert removal['forum_validated_by'] is None
        assert removal['status'] == 'in_progress'
        assert removal['ready_at'] is None
        assert [e['action'] for e in removal['history']] == ['create']
        # the author validates nothing
        assert removal['can'] == {
            'validate': [],
            'unvalidate': [],
            'update': True,
            'cancel': True,
        }

        saved = session.get(AccountRemovalRequest, removal['id'])
        assert saved.user_name == 'Contributor'

    def test_create_merge(self, client, user_ids):
        # the forum account of the target is found by the API
        body = body_for(
            user_ids['contributor'],
            reason='merge',
            target_user_id=user_ids['moderator'],
        )
        removal = post(client, self.PREFIX, body, 'contributor2').json
        assert removal['target_user_id'] == user_ids['moderator']
        assert removal['target_forum_id'] == forum_id(user_ids['moderator'])

    def test_targets(self, client, user_ids, discourse):
        user_id = user_ids['contributor']

        # a merge needs its target
        body = body_for(user_id, reason='merge')
        post(client, self.PREFIX, body, 'moderator', status=400)

        # a forum account to merge into which is not the one of the target
        body = body_for(
            user_id,
            reason='merge',
            target_user_id=user_ids['moderator'],
            target_forum_id=CLOSED_FORUM_ID,
        )
        post(client, self.PREFIX, body, 'moderator', status=400)

        # an anonymization into another account than the closed one
        body = body_for(user_id, target_user_id=user_ids['moderator'])
        post(client, self.PREFIX, body, 'moderator', status=400)

        # the target has no forum account
        discourse.get_userid = Mock(side_effect=not_found())
        body = body_for(user_id, reason='merge', target_user_id=user_ids['moderator'])
        post(client, self.PREFIX, body, 'moderator', status=400)

        # the forum does not answer
        discourse.get_userid = Mock(side_effect=Exception('down'))
        post(client, self.PREFIX, body, 'moderator', status=503)

    def test_create_as_forum_moderator(self, client, user_ids):
        body = body_for(user_ids['contributor'])
        post(client, self.PREFIX, body, 'contributor2')

    def test_create_twice(self, client, user_ids):
        body = body_for(user_ids['contributor'])
        post(client, self.PREFIX, body, 'moderator')
        post(client, self.PREFIX, body, 'moderator', status=409)

    def test_create_invalid(self, client, user_ids, closed_account):
        user_id = user_ids['contributor']

        # into itself
        body = body_for(user_id, reason='merge', target_user_id=user_id)
        post(client, self.PREFIX, body, 'moderator', status=400)
        body = body_for(closed_account)
        post(client, self.PREFIX, body, 'moderator', status=400)

        # unknown users
        body = body_for(-1)
        post(client, self.PREFIX, body, 'moderator', status=400)
        body = body_for(user_id, reason='merge', target_user_id=-1)
        post(client, self.PREFIX, body, 'moderator', status=400)

        # a moderator of the topoguide, of the forum
        body = body_for(user_ids['moderator'])
        post(client, self.PREFIX, body, 'contributor2', status=400)
        body = body_for(user_ids['contributor3'])
        post(client, self.PREFIX, body, 'moderator', status=400)

        # in the past
        body = body_for(user_id, executable_after=future(-1))
        post(client, self.PREFIX, body, 'moderator', status=400)

        # reason
        body = body_for(user_id, reason='because')
        post(client, self.PREFIX, body, 'moderator', status=422)

        # a link shown to the other moderators: http(s) only
        body = body_for(user_id, forum_url='javascript:alert(1)')
        post(client, self.PREFIX, body, 'moderator', status=422)

    def test_user_request_date(self, client, user_ids):
        user_id = user_ids['contributor']

        # an anonymization needs when the user asked for it
        body = body_for(user_id, user_request_date=None)
        post(client, self.PREFIX, body, 'moderator', status=400)
        # not in the future
        body = body_for(
            user_id, user_request_date=future(1), executable_after=future(9)
        )
        post(client, self.PREFIX, body, 'moderator', status=400)
        # done 7 days after it at the earliest
        body = body_for(
            user_id, user_request_date=future(-3), executable_after=future(3)
        )
        post(client, self.PREFIX, body, 'moderator', status=400)
        body = body_for(
            user_id, user_request_date=future(-3), executable_after=future(4)
        )
        removal = post(client, self.PREFIX, body, 'moderator').json
        assert removal['user_request_date'] == future(-3)

    def test_spam_without_user_request(self, client, user_ids):
        body = body_for(
            user_ids['contributor'],
            reason='spam',
            user_request_date=None,
            executable_after=future(0),
        )
        removal = post(client, self.PREFIX, body, 'moderator').json
        assert removal['user_request_date'] is None

    def test_forum_down(self, client, user_ids, discourse):
        # whether the account is a moderator of the forum cannot be checked
        discourse.is_moderator = Mock(side_effect=Exception('down'))
        body = body_for(user_ids['contributor'])
        post(client, self.PREFIX, body, 'moderator', status=503)


def create(client, user_ids, **kwargs):
    body = body_for(user_ids['contributor'], **kwargs)
    return post(client, '/users/removals', body, 'moderator').json['id']


def url(request_id, action=''):
    return f'/users/removals/{request_id}' + (f'/{action}' if action else '')


class TestValidate:
    def test_validate_both_sides(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)

        # contributor2 (a moderator of the topoguide) validates the topoguide
        body = {'side': 'topoguide'}
        removal = post(client, url(request_id, 'validate'), body, 'contributor2').json
        assert removal['topoguide_validated_by']['id'] == user_ids['contributor2']
        assert removal['topoguide_validated_at'] is not None
        assert removal['status'] == 'in_progress'
        # not the other side: a person validates one side only
        assert removal['can']['validate'] == []
        assert removal['can']['unvalidate'] == ['topoguide']

        # contributor3 (a moderator of the forum) validates the forum
        body = {'side': 'forum'}
        removal = post(client, url(request_id, 'validate'), body, 'contributor3').json
        assert removal['forum_validated_by']['id'] == user_ids['contributor3']
        assert removal['status'] == 'validated'
        # the date, or a day after the last validation
        assert removal['ready_at'] >= removal['forum_validated_at']
        assert [e['action'] for e in removal['history']] == [
            'create',
            'validate',
            'validate',
        ]

    def test_author_cannot_validate(self, client, user_ids):
        request_id = create(client, user_ids)
        body = {'side': 'topoguide'}
        post(client, url(request_id, 'validate'), body, 'moderator', status=403)

    def test_not_a_moderator_of_the_side(self, client, user_ids):
        request_id = create(client, user_ids)
        # contributor3 is a moderator of the forum, not of the topoguide
        body = {'side': 'topoguide'}
        post(client, url(request_id, 'validate'), body, 'contributor3', status=403)

    def test_one_side_by_person(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)

        # contributor2 is a moderator of both: he validates only one side
        post(client, url(request_id, 'validate'), {'side': 'topoguide'}, 'contributor2')
        body = {'side': 'forum'}
        post(client, url(request_id, 'validate'), body, 'contributor2', status=403)

    def test_already_validated(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)
        body = {'side': 'topoguide'}
        post(client, url(request_id, 'validate'), body, 'contributor2')
        post(client, url(request_id, 'validate'), body, 'contributor2', status=409)

    @pytest.mark.parametrize('field', ['done_at', 'cancelled_at'])
    def test_closed(self, client, session, user_ids, second_moderator, field):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        setattr(removal, field, datetime.datetime.now(datetime.UTC))
        session.flush()

        body = {'side': 'topoguide'}
        post(client, url(request_id, 'validate'), body, 'contributor2', status=400)

    def test_unknown(self, client, second_moderator):
        body = {'side': 'topoguide'}
        post(client, url(999999, 'validate'), body, 'contributor2', status=404)

    def test_forum_down(self, client, user_ids, discourse):
        request_id = create(client, user_ids)
        discourse.is_moderator = Mock(side_effect=Exception)
        body = {'side': 'forum'}
        post(client, url(request_id, 'validate'), body, 'contributor3', status=503)


class TestUnvalidate:
    def test_unvalidate(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids, forum_url='https://f.org/1')
        body = {'side': 'topoguide'}
        post(client, url(request_id, 'validate'), body, 'contributor2')

        # the discussion of the request is the same
        removal = post(client, url(request_id, 'unvalidate'), body, 'contributor2').json
        assert removal['topoguide_validated_by'] is None
        assert removal['forum_url'] == 'https://f.org/1'
        assert removal['status'] == 'in_progress'

        # a new one can be given: the previous one stays in the history
        post(client, url(request_id, 'validate'), body, 'contributor2')
        body['forum_url'] = 'https://forum.camptocamp.org/t/2'
        removal = post(client, url(request_id, 'unvalidate'), body, 'contributor2').json
        assert removal['forum_url'] == 'https://forum.camptocamp.org/t/2'
        assert [e.get('forum_url') for e in removal['history']] == [
            'https://f.org/1',
            None,
            None,
            None,
            'https://forum.camptocamp.org/t/2',
        ]

    def test_not_validated(self, client, user_ids, second_moderator):
        request_id = create(client, user_ids)
        body = {'side': 'topoguide', 'forum_url': 'https://f.org/1'}
        post(client, url(request_id, 'unvalidate'), body, 'contributor2', status=400)

    def test_done(self, client, session, user_ids, second_moderator):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        removal.topoguide_validated_by = user_ids['contributor2']
        removal.done_at = datetime.datetime.now(datetime.UTC)
        session.flush()

        body = {'side': 'topoguide', 'forum_url': 'https://f.org/1'}
        post(client, url(request_id, 'unvalidate'), body, 'contributor2', status=400)


class TestUpdateAndCancel:
    def test_update_forum_url(self, client, user_ids):
        request_id = create(client, user_ids)
        headers = auth_headers(username='moderator')
        body = {'forum_url': 'https://forum.camptocamp.org/t/3'}
        response = send_json(client, 'put', url(request_id), body, headers=headers)
        assert response.json['forum_url'] == 'https://forum.camptocamp.org/t/3'

    def test_update_validated(self, client, session, user_ids):
        request_id = create(client, user_ids)
        removal = session.get(AccountRemovalRequest, request_id)
        removal.topoguide_validated_by = user_ids['moderator']
        removal.forum_validated_by = user_ids['contributor3']
        session.flush()

        headers = auth_headers(username='moderator')
        body = {'forum_url': 'https://forum.camptocamp.org/t/3'}
        send_json(client, 'put', url(request_id), body, headers=headers, status=400)

    def test_cancel(self, client, session, user_ids):
        request_id = create(client, user_ids)

        removal = post(client, url(request_id, 'cancel'), {}, 'contributor3').json

        # kept, cancelled
        assert removal['status'] == 'cancelled'
        assert removal['cancelled_by']['id'] == user_ids['contributor3']
        assert removal['can'] == {
            'validate': [],
            'unvalidate': [],
            'update': False,
            'cancel': False,
        }
        assert session.get(AccountRemovalRequest, request_id) is not None
        post(client, url(request_id, 'cancel'), {}, 'contributor3', status=400)

        # a new request is possible again
        create(client, user_ids)

    def test_cancel_unauthorized(self, client, user_ids):
        request_id = create(client, user_ids)
        body = {'forum_url': 'https://forum.camptocamp.org/t/4'}
        post(client, url(request_id, 'cancel'), body, 'contributornotos', status=403)


class TestRead:
    PREFIX = '/users/removals'

    def test_unauthorized(self, client):
        client.get(self.PREFIX, status=403)

        headers = auth_headers(username='contributornotos')
        client.get(self.PREFIX, headers=headers, status=403)

    def test_list(self, client, user_ids):
        request_id = create(client, user_ids)

        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX, headers=headers, status=200)
        assert response.json['total'] == 1
        assert [r['id'] for r in response.json['removals']] == [request_id]
        removal = response.json['removals'][0]
        assert removal['requested_by'] == {
            'id': user_ids['moderator'],
            'name': 'Moderator',
        }
        assert response.json['roles'] == {'topoguide': True, 'forum': False}

        # a moderator of the forum: what they can do with it
        headers = auth_headers(username='contributor3')
        response = client.get(self.PREFIX, headers=headers, status=200)
        assert response.json['roles'] == {'topoguide': False, 'forum': True}
        assert response.json['removals'][0]['can']['validate'] == ['forum']

    def test_list_status_and_paging(self, client, session, user_ids):
        cancelled_id = create(client, user_ids)
        body = {'forum_url': 'https://forum.camptocamp.org/t/4'}
        post(client, url(cancelled_id, 'cancel'), body, 'moderator')
        open_id = create(client, user_ids)

        headers = auth_headers(username='moderator')

        def ids(query):
            response = client.get(self.PREFIX + query, headers=headers, status=200)
            return [r['id'] for r in response.json['removals']]

        # the open ones first
        assert ids('') == [open_id, cancelled_id]
        assert ids('?status=in_progress') == [open_id]
        assert ids('?status=cancelled') == [cancelled_id]
        assert ids('?status=validated') == []
        assert ids('?offset=1&limit=1') == [cancelled_id]
        client.get(self.PREFIX + '?status=gone', headers=headers, status=422)

    def test_count(self, client, user_ids):
        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json == {
            'open': 0,
            'roles': {'topoguide': True, 'forum': False},
        }

        create(client, user_ids)
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json['open'] == 1

        # a moderator of the forum only
        headers = auth_headers(username='contributor3')
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json == {
            'open': 1,
            'roles': {'topoguide': False, 'forum': True},
        }

        # neither of the topoguide nor of the forum
        headers = auth_headers(username='contributornotos')
        client.get(self.PREFIX + '/count', headers=headers, status=403)

    def test_count_forum_down(self, client, discourse):
        # a moderator of the topoguide still gets it, a user gets a 503
        discourse.is_moderator = Mock(side_effect=Exception('down'))
        headers = auth_headers(username='moderator')
        response = client.get(self.PREFIX + '/count', headers=headers, status=200)
        assert response.json['roles'] == {'topoguide': True, 'forum': False}
        headers = auth_headers(username='contributornotos')
        client.get(self.PREFIX + '/count', headers=headers, status=503)
