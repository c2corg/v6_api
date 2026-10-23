import datetime
import types
from unittest.mock import patch

from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest


class _Clock:
    """A clock that only moves when the test says so."""

    def __init__(self):
        self.now = datetime.datetime.now(datetime.UTC)

    def advance(self, seconds):
        self.now += datetime.timedelta(seconds=seconds)

    def datetime_module(self):
        # stands in for the `datetime` module imported by the tween: only
        # `datetime.now()` is redirected to this clock
        clock = self

        class _Datetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now.astimezone(tz)

        return types.SimpleNamespace(
            datetime=_Datetime, timedelta=datetime.timedelta, UTC=datetime.UTC
        )


class RateLimitingTest(BaseTestRest):
    def setUp(self):
        BaseTestRest.setUp(self)

        # The rate limiting window is a few seconds long in the tests: with
        # the real clock it could expire in the middle of a test on a slow
        # run, so the tween reads the time from a clock the test controls.
        self.clock = _Clock()
        clock_patch = patch(
            'c2corg_api.tweens.rate_limiting.datetime', self.clock.datetime_module()
        )
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self._prefix = '/waypoints'

        self.username = None
        self.user = None

        self.limit = int(self.settings['rate_limiting.limit'])
        self.limit_moderator = int(self.settings['rate_limiting.limit_moderator'])
        self.limit_robot = int(self.settings['rate_limiting.limit_robot'])
        self.window_span = int(self.settings['rate_limiting.window_span'])
        self.max_times = int(self.settings['rate_limiting.max_times'])

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_contributor(self, _send_email):
        self._set_user('contributor')
        self._test_requests()
        _send_email.assert_called_once()

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_moderator(self, _send_email):
        self._set_user('moderator')
        self._test_requests()
        _send_email.assert_called_once()

    def _test_requests(self):
        limit = (
            self.limit_robot
            if self.user.robot
            else self.limit_moderator
            if self.user.moderator
            else self.limit
        )

        # Check contributor has no rate limiting data yet
        assert self.user.ratelimit_remaining is None
        assert self.user.ratelimit_reset is None

        self._create_document()

        # Check rating limiting data are now available
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == limit - 1

        expiration_date = self.user.ratelimit_reset
        assert expiration_date == self.clock.now + datetime.timedelta(
            seconds=self.window_span
        )

        # Make as many requests as allowed according to the settings
        # (already 1 request as been consumed when creating the document)
        for i in range(1, limit):
            self._update_document()
            self.session.refresh(self.user)
            assert self.user.ratelimit_remaining == limit - 1 - i
            assert self.user.ratelimit_reset == expiration_date

        # Counter "remaining" is now set to 0 => write requests should be
        # refused with error code 429 ("Too many requests")
        assert self.user.ratelimit_remaining == 0
        self._update_document(status=429)
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == 0

        # GET requests are still allowed
        document_id = self.document['document_id']
        self.app.get(self._prefix + '/' + str(document_id), status=200)

        # Test write requests are accepted again after window is expired
        self._wait()
        self._update_document()
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == limit - 1

        # Deleting the document is also considered by rate limiting
        # (only tested for moderators to skip permission issues)
        if self.user.moderator:
            self._delete_document()
            self.session.refresh(self.user)
            assert self.user.ratelimit_remaining == limit - 2

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_blocked(self, _send_email):
        """Check that user is blocked if rate limited too many times"""
        self._set_user('contributor')
        self._create_document()
        self.session.refresh(self.user)

        for n in range(0, self.max_times + 1):
            assert not self.user.blocked
            self._wait()
            for i in range(0, self.limit):
                self._update_document()
                self.session.refresh(self.user)
                assert self.user.ratelimit_remaining == self.limit - 1 - i
            self._update_document(status=429)
            self.session.refresh(self.user)
            assert self.user.ratelimit_times == n + 1

        # User has reached their max number of allowed rate limited windows
        # thus is now blocked:
        assert self.user.blocked
        assert self.user.ratelimit_times == self.max_times + 1
        # Two emails have been set for each rate limited windows, and one
        # after the user has been blocked
        assert _send_email.call_count == 3
        user_profile = f'{self.settings["ui.url"]}/profiles/{self.user.id}'
        _send_email.assert_called_with(
            'fixme@camptocamp.org',
            subject="Un usage excessif de l'API a été détecté",
            body=(
                'Bonjour\n\n'
                f'Le contributeur {self.user.name} a atteint une '
                'nouvelle fois le nombre maximum autorisé de modifications '
                "via l'API camptocamp.org.\n"
                'Il a également dépassé le nombre maximum autorisé '
                'de blocages temporaires et a donc été '
                'définitivement bloqué.\nSon profil : '
                f'{user_profile}'
            ),
        )
        self._update_document(status=403)

    def _create_document(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 2203,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [{'lang': 'en', 'title': 'Mont Granier'}],
        }
        headers = self.add_authorization_header(username=self.username)
        response = self.app_post_json(self._prefix, body, headers=headers, status=200)
        document_id = response.json.get('document_id')
        self._set_document(document_id)

    def _update_document(self, status=200):
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
        headers = self.add_authorization_header(username=self.username)
        self.app_put_json(
            self._prefix + '/' + str(document_id), body, headers=headers, status=status
        )
        self._set_document(document_id)

    def _set_document(self, document_id):
        response = self.app.get(self._prefix + '/' + str(document_id), status=200)
        self.document = response.json

    def _delete_document(self):
        headers = self.add_authorization_header(username=self.username)
        self.app.delete_json(
            '/documents/delete/' + str(self.document['document_id']),
            headers=headers,
            status=200,
        )

    def _wait(self):
        # let the rate limiting window expire
        self.clock.advance(self.window_span + 1)

    def _set_user(self, username):
        self.username = username
        user_id = self.global_userids[username]
        self.user = self.session.get(User, user_id)
