import datetime
import types
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers, send_json

PREFIX = '/waypoints'


class _Clock:
    """A clock that only moves when the test says so."""

    def __init__(self):
        self.now = datetime.datetime.now(datetime.UTC)

    def advance(self, seconds):
        self.now += datetime.timedelta(seconds=seconds)

    def datetime_module(self):
        # stands in for the `datetime` module imported by the rate limiting: only
        # `datetime.now()` is redirected to this clock
        clock = self

        class _Datetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now.astimezone(tz)

        return types.SimpleNamespace(
            datetime=_Datetime, timedelta=datetime.timedelta, UTC=datetime.UTC
        )


@dataclass(frozen=True)
class Limits:
    """The rate limiting settings of the tests."""

    limit: int
    limit_moderator: int
    limit_robot: int
    window_span: int
    max_times: int

    def of(self, user):
        if user.robot:
            return self.limit_robot
        return self.limit_moderator if user.moderator else self.limit


class _Writer:
    """Writes a waypoint as a user, and keeps its last version."""

    def __init__(self, client, username):
        self.client = client
        self.username = username
        self.document = None

    def create(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 2203,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [{'lang': 'en', 'title': 'Mont Granier'}],
        }
        headers = auth_headers(username=self.username)
        response = send_json(
            self.client, 'post', PREFIX, body, headers=headers, status=200
        )
        self._reload(response.json.get('document_id'))

    def update(self, status=200):
        document_id = self.document['document_id']
        body = {
            'message': 'Update',
            'document': {
                'document_id': document_id,
                'version': self.document['version'],
                'waypoint_type': 'summit',
                'elevation': self.document['elevation'] + 1,
                'locales': [
                    {
                        'version': self.document['locales'][0]['version'],
                        'lang': 'en',
                        'title': 'Mont Granier',
                    }
                ],
            },
        }
        headers = auth_headers(username=self.username)
        send_json(
            self.client,
            'put',
            f'{PREFIX}/{document_id}',
            body,
            headers=headers,
            status=status,
        )
        self._reload(document_id)

    def delete(self):
        headers = auth_headers(username=self.username)
        self.client.delete_json(
            '/documents/delete/' + str(self.document['document_id']),
            headers=headers,
            status=200,
        )

    def _reload(self, document_id):
        response = self.client.get(f'{PREFIX}/{document_id}', status=200)
        self.document = response.json


@pytest.fixture
def clock(client):
    """Let the rate limiting read the time from a clock the test moves."""
    # The rate limiting window is a few seconds long in the tests: with the
    # real clock it could expire in the middle of a test on a slow run.
    clock = _Clock()
    with patch('c2corg_api.security.rate_limiting.datetime', clock.datetime_module()):
        yield clock


@pytest.fixture
def limits(settings) -> Limits:
    """Return the rate limiting settings."""
    return Limits(
        limit=int(settings['rate_limiting.limit']),
        limit_moderator=int(settings['rate_limiting.limit_moderator']),
        limit_robot=int(settings['rate_limiting.limit_robot']),
        window_span=int(settings['rate_limiting.window_span']),
        max_times=int(settings['rate_limiting.max_times']),
    )


def _wait(clock, limits):
    # let the rate limiting window expire
    clock.advance(limits.window_span + 1)


def _check_requests(client, session, clock, limits, user, username):
    writer = _Writer(client, username)
    limit = limits.of(user)

    # Check the user has no rate limiting data yet
    assert user.ratelimit_remaining is None
    assert user.ratelimit_reset is None

    writer.create()

    # Check rating limiting data are now available
    session.refresh(user)
    assert user.ratelimit_remaining == limit - 1

    expiration_date = user.ratelimit_reset
    assert expiration_date == clock.now + datetime.timedelta(seconds=limits.window_span)

    # Make as many requests as allowed according to the settings
    # (already 1 request as been consumed when creating the document)
    for i in range(1, limit):
        writer.update()
        session.refresh(user)
        assert user.ratelimit_remaining == limit - 1 - i
        assert user.ratelimit_reset == expiration_date

    # Counter "remaining" is now set to 0 => write requests should be
    # refused with error code 429 ("Too many requests")
    assert user.ratelimit_remaining == 0
    writer.update(status=429)
    session.refresh(user)
    assert user.ratelimit_remaining == 0

    # GET requests are still allowed
    client.get(f'{PREFIX}/{writer.document["document_id"]}', status=200)

    # Test write requests are accepted again after window is expired
    _wait(clock, limits)
    writer.update()
    session.refresh(user)
    assert user.ratelimit_remaining == limit - 1

    # Deleting the document is also considered by rate limiting
    # (only tested for moderators to skip permission issues)
    if user.moderator:
        writer.delete()
        session.refresh(user)
        assert user.ratelimit_remaining == limit - 2


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_contributor(_send_email, client, session, user_ids, clock, limits):
    user = session.get(User, user_ids['contributor'])
    _check_requests(client, session, clock, limits, user, 'contributor')
    _send_email.assert_called_once()


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_moderator(_send_email, client, session, user_ids, clock, limits):
    user = session.get(User, user_ids['moderator'])
    _check_requests(client, session, clock, limits, user, 'moderator')
    _send_email.assert_called_once()


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_blocked(_send_email, client, session, settings, user_ids, clock, limits):
    """Check that user is blocked if rate limited too many times"""
    user = session.get(User, user_ids['contributor'])
    writer = _Writer(client, 'contributor')
    writer.create()
    session.refresh(user)

    for n in range(0, limits.max_times + 1):
        assert not user.blocked
        _wait(clock, limits)
        for i in range(0, limits.limit):
            writer.update()
            session.refresh(user)
            assert user.ratelimit_remaining == limits.limit - 1 - i
        writer.update(status=429)
        session.refresh(user)
        assert user.ratelimit_times == n + 1

    # User has reached their max number of allowed rate limited windows
    # thus is now blocked:
    assert user.blocked
    assert user.ratelimit_times == limits.max_times + 1
    # Two emails have been set for each rate limited windows, and one
    # after the user has been blocked
    assert _send_email.call_count == 3
    user_profile = f'{settings["ui.url"]}/profiles/{user.id}'
    _send_email.assert_called_with(
        'fixme@camptocamp.org',
        subject="Un usage excessif de l'API a été détecté",
        body=(
            'Bonjour\n\n'
            f'Le contributeur {user.name} a atteint une '
            'nouvelle fois le nombre maximum autorisé de modifications '
            "via l'API camptocamp.org.\n"
            'Il a également dépassé le nombre maximum autorisé '
            'de blocages temporaires et a donc été '
            'définitivement bloqué.\nSon profil : '
            f'{user_profile}'
        ),
    )
    writer.update(status=403)
