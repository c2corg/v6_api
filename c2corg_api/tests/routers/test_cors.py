"""
Integration tests for CORS on the FastAPI application.

These tests exercise the **real** ``create_app()`` factory so that we
verify the ``CORSMiddleware`` is actually wired into the production app,
not just a test-only surrogate.

The ``CORSMiddleware`` configuration in ``c2corg_api.app.create_app``
should mirror the legacy Pyramid/Cornice ``cors_policy``:

    allow_origins = ["*"]
    allow_methods = ["*"]
    allow_headers = ["Content-Type"]
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestCORSIntegration(BaseTestCase):
    """Verify that CORS headers are returned by the real app."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    # ── preflight (OPTIONS) ──────────────────────────────────────

    def test_preflight_returns_allow_origin(self):
        """OPTIONS preflight with ``Origin`` → CORS header."""
        resp = self.client.options(
            '/v2/books',
            headers={
                'Origin': 'https://www.camptocamp.org',
                'Access-Control-Request-Method': 'GET',
            },
        )
        assert resp.status_code in (200, 204)
        assert resp.headers.get('access-control-allow-origin') == '*'

    def test_preflight_allows_content_type_header(self):
        """Preflight requesting ``Content-Type`` is accepted."""
        resp = self.client.options(
            '/v2/books',
            headers={
                'Origin': 'https://www.camptocamp.org',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            },
        )
        assert resp.status_code in (200, 204)
        allowed = resp.headers.get('access-control-allow-headers', '').lower()
        assert 'content-type' in allowed

    def test_preflight_rejects_disallowed_header(self):
        """Preflight with a header not in ``allow_headers``
        must NOT echo it back.
        """
        resp = self.client.options(
            '/v2/books',
            headers={
                'Origin': 'https://www.camptocamp.org',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'X-Custom-Secret',
            },
        )
        allowed = resp.headers.get('access-control-allow-headers', '').lower()
        assert 'x-custom-secret' not in allowed

    def test_preflight_allows_all_methods(self):
        """``allow_methods=["*"]`` accepts any method."""
        for method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
            with self.subTest(method=method):
                resp = self.client.options(
                    '/v2/books',
                    headers={
                        'Origin': 'https://example.com',
                        'Access-Control-Request-Method': method,
                    },
                )
                assert resp.status_code in (200, 204)
                assert resp.headers.get('access-control-allow-origin') == '*'

    # ── simple / actual requests ─────────────────────────────────

    def test_simple_get_includes_allow_origin(self):
        """A 200 GET with ``Origin`` includes CORS header."""
        resp = self.client.get(
            '/v2/books', headers={'Origin': 'https://www.camptocamp.org'}
        )
        assert resp.status_code == 200
        assert resp.headers.get('access-control-allow-origin') == '*'

    def test_any_origin_is_allowed(self):
        """``allow_origins=["*"]`` reflects for any origin."""
        for origin in (
            'https://www.camptocamp.org',
            'http://localhost:3000',
            'https://evil.example.com',
        ):
            with self.subTest(origin=origin):
                resp = self.client.get('/v2/books', headers={'Origin': origin})
                assert resp.status_code == 200
                assert resp.headers.get('access-control-allow-origin') == '*'

    def test_no_origin_means_no_cors_headers(self):
        """No ``Origin`` header → no CORS response headers."""
        resp = self.client.get('/v2/books')
        assert 'access-control-allow-origin' not in resp.headers

    # ── error responses must include CORS headers ────────────────

    def test_401_corrupted_token_includes_cors(self):
        """Corrupted JWT → 401 with CORS headers.

        Without CORS on error responses the browser hides the
        status code from JavaScript SPA clients.
        """
        resp = self.client.post(
            '/v2/books',
            json={},
            headers={
                'Origin': 'https://www.camptocamp.org',
                'Authorization': 'JWT this.is.corrupted',
            },
        )
        assert resp.status_code == 401
        assert resp.headers.get('access-control-allow-origin') == '*'

    def test_401_expired_token_includes_cors(self):
        """Expired JWT → 401 with CORS headers."""
        from datetime import datetime, timezone

        import jwt as pyjwt

        secret = settings.get('jwt.private_key', 'CHANGE_ME_TO_A_REAL_SECRET______')
        expired_token = pyjwt.encode(
            {'sub': '99999', 'exp': datetime(2020, 1, 1, tzinfo=timezone.utc)},
            secret,
            algorithm='HS256',
        )
        resp = self.client.post(
            '/v2/books',
            json={},
            headers={
                'Origin': 'https://www.camptocamp.org',
                'Authorization': f'JWT {expired_token}',
            },
        )
        assert resp.status_code == 401
        assert resp.headers.get('access-control-allow-origin') == '*'

    def test_500_includes_cors(self):
        """Unhandled server error → 500 with CORS headers.

        Starlette's ``ServerErrorMiddleware`` intercepts 500s
        before ``CORSMiddleware`` can decorate them.  The
        ``_unhandled_exception_handler`` in ``app.py`` works
        around this by setting the header explicitly.
        """
        app = self._get_app()

        # Temporarily override get_db to raise an exception,
        # simulating an unhandled server error.
        def _bomb():
            raise RuntimeError('Simulated failure')

        app.dependency_overrides[get_db] = _bomb

        try:
            resp = self.client.get(
                '/v2/books', headers={'Origin': 'https://www.camptocamp.org'}
            )
            assert resp.status_code == 500
            assert resp.headers.get('access-control-allow-origin') == '*'
        finally:
            # Restore the normal override for other tests.
            def _override_get_db():
                yield self.session

            app.dependency_overrides[get_db] = _override_get_db

    # ── parity with Pyramid cors_policy ──────────────────────────

    def test_parity_origins_match_pyramid(self):
        """FastAPI ``allow_origins`` = ``["*"]`` matches
        Pyramid ``cors_policy = dict(origins=('*'), ...)``.
        """
        resp = self.client.options(
            '/v2/books',
            headers={
                'Origin': 'https://anything.example.com',
                'Access-Control-Request-Method': 'GET',
            },
        )
        assert resp.headers.get('access-control-allow-origin') == '*'

    def test_parity_content_type_allowed(self):
        """FastAPI ``allow_headers`` includes ``Content-Type``,
        matching the Pyramid ``cors_policy``.
        """
        resp = self.client.options(
            '/v2/books',
            headers={
                'Origin': 'https://anything.example.com',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            },
        )
        assert resp.status_code in (200, 204)
        allowed = resp.headers.get('access-control-allow-headers', '').lower()
        assert 'content-type' in allowed
