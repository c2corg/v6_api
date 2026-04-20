"""
FastAPI rate-limiting tests.

Mirrors ``c2corg_api/tests/tweens/test_rate_limiting.py`` — same
assertions — but exercises the rate-limiting logic integrated into
``get_current_user`` instead of the Pyramid tween.

Uses ``fastapi.testclient.TestClient`` against the **real** application
built by ``create_app()`` so that CORS, auth, and the full dependency
chain are exercised.

Only ``get_db`` is overridden so that tests share the
transaction-scoped session from ``BaseTestCase`` (per-test rollback).
Authentication uses the real JWT tokens created by ``setup_package()``.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.rate_limiting import configure_rate_limiting
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class RateLimitingTest(BaseTestCase):
    """Rate-limiting tests"""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):  # noqa
        super().setUp()
        self._prefix = '/v2/books'

        configure_security(settings)
        configure_rate_limiting(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

        self.username = None
        self.user = None

        self.limit = int(settings['rate_limiting.limit'])
        self.limit_moderator = int(settings['rate_limiting.limit_moderator'])
        self.limit_robot = int(settings.get('rate_limiting.limit_robot', 1000))
        self.window_span = int(settings['rate_limiting.window_span'])
        self.max_times = int(settings['rate_limiting.max_times'])

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username=None):
        username = username or self.username
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ── per-role tests ───────────────────────────────────────────

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

        # User has no rate-limiting data yet
        assert self.user.ratelimit_remaining is None
        assert self.user.ratelimit_reset is None

        self._create_document()

        # Rate-limiting data should now be available
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == limit - 1

        expiration_date = self.user.ratelimit_reset
        delta = (
            datetime.now(timezone.utc)
            + timedelta(seconds=self.window_span)
            - self.user.ratelimit_reset
        )
        assert delta.total_seconds() <= 2

        # Consume remaining requests (1 was already used for the create)
        for i in range(1, limit):
            self._update_document()
            self.session.refresh(self.user)
            assert self.user.ratelimit_remaining == limit - 1 - i
            assert self.user.ratelimit_reset == expiration_date

        # Counter is now 0 → 429
        assert self.user.ratelimit_remaining == 0
        self._update_document(expected_status=429)
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == 0

        # GET requests are still allowed
        document_id = self.document['document_id']
        resp = self.client.get(f'{self._prefix}/{document_id}')
        assert resp.status_code == 200

        # After window expires, writes should be accepted again
        self._wait()
        self._update_document()
        self.session.refresh(self.user)
        assert self.user.ratelimit_remaining == limit - 1

    # ── blocking test ────────────────────────────────────────────

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_blocked(self, _send_email):
        """User is blocked after being rate-limited too many times."""
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
            self._update_document(expected_status=429)
            self.session.refresh(self.user)
            assert self.user.ratelimit_times == n + 1

        # User has now been blocked
        assert self.user.blocked
        assert self.user.ratelimit_times == self.max_times + 1

        # One e-mail per rate-limited window + one for the block
        assert _send_email.call_count == 3

        user_profile = f'{settings["ui.url"]}/profiles/{self.user.id}'
        _send_email.assert_called_with(
            'fixme@camptocamp.org',
            subject="Un usage excessif de l'API a été détecté",
            body=(
                'Bonjour\n\n'
                f'Le contributeur {self.user.name} a atteint une '
                'nouvelle fois le nombre maximum autorisé de '
                "modifications via l'API camptocamp.org.\n"
                'Il a également dépassé le nombre maximum autorisé '
                'de blocages temporaires et a donc été '
                'définitivement bloqué.\nSon profil : '
                f'{user_profile}'
            ),
        )

        # Blocked user → 403 (from auth layer)
        self._update_document(expected_status=403)

    # ── helpers ──────────────────────────────────────────────────

    def _create_document(self):
        body = {
            'book_types': ['biography'],
            'locales': [{'lang': 'en', 'title': 'Rate-limit book'}],
        }
        headers = self._auth_headers()
        resp = self.client.post(self._prefix, json=body, headers=headers)
        assert resp.status_code == 200, f'Create failed: {resp.status_code} {resp.text}'
        document_id = resp.json()['document_id']
        self._refresh_document(document_id)

    def _update_document(self, expected_status=200):
        document_id = self.document['document_id']
        body = {
            'message': 'Update',
            'document': {
                'document_id': document_id,
                'version': self.document['version'],
                'book_types': ['biography'],
                'locales': [
                    {
                        'version': self.document['locales'][0]['version'],
                        'lang': 'en',
                        'title': 'Rate-limit book',
                    }
                ],
            },
        }
        headers = self._auth_headers()
        resp = self.client.put(
            f'{self._prefix}/{document_id}', json=body, headers=headers
        )
        assert resp.status_code == expected_status, (
            f'Expected {expected_status}, got {resp.status_code}: {resp.text}'
        )
        if expected_status == 200:
            self._refresh_document(document_id)

    def _refresh_document(self, document_id):
        resp = self.client.get(f'{self._prefix}/{document_id}')
        assert resp.status_code == 200
        self.document = resp.json()

    def _wait(self):
        waiting_time = self.window_span + 1
        print(
            'Waiting %d secs for the rate-limiting window to expire...' % waiting_time
        )
        time.sleep(waiting_time)

    def _set_user(self, username):
        self.username = username
        user_id = global_userids[username]
        self.user = self.session.get(User, user_id)
