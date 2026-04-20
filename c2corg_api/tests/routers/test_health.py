"""
Tests for the FastAPI health router (``/v2/health``).

Mirrors ``c2corg_api/tests/views/test_health.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.routers.health import configure_health
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestHealthFastAPIRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)
        configure_health(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def test_get(self):
        r = self.client.get('/v2/health')
        assert r.status_code == 200

        data = r.json()

        assert data['es'] == 'ok'
        assert data['redis'] == 'ok'
