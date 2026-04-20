"""
Tests for the FastAPI cooker router (``/v2/cooker``).

Mirrors ``c2corg_api/tests/views/test_cooker.py`` and adds tests for the
input-validation hardening (body type, key count, value length).
"""

from fastapi.testclient import TestClient

from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestCookerFastAPIRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        app = self._get_app()
        self.client = TestClient(app, raise_server_exceptions=False)

    # ── functional (mirrors Pyramid test) ────────────────────────

    def test_post(self):
        markdowns = {'lang': 'fr', 'description': '**strong emphasis** and *emphasis*'}
        r = self.client.post('/v2/cooker', json=markdowns)
        assert r.status_code == 200

        htmls = r.json()

        # lang is not a markdown field, it must be untouched
        assert markdowns['lang'] == htmls['lang']
        assert markdowns['description'] != htmls['description']
        assert '<strong>' in htmls['description']
        assert '<em>' in htmls['description']

    def test_non_string_values_pass_through(self):
        body = {'lang': 'en', 'version': 42, 'description': '# Title'}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 200

        result = r.json()
        assert result['version'] == 42
        assert result['lang'] == 'en'

    def test_empty_body(self):
        r = self.client.post('/v2/cooker', json={})
        assert r.status_code == 200
        assert r.json() == {}

    def test_xss_sanitised(self):
        body = {'description': '<script>alert("xss")</script>hello'}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 200
        result = r.json()
        assert '<script>' not in result['description']
        assert 'hello' in result['description']

    def test_not_markdown_properties_are_untouched(self):
        """Keys listed in NOT_MARKDOWN_PROPERTY must pass through
        without any Markdown processing, even when their values
        contain valid Markdown syntax.
        """
        body = {
            'lang': 'fr',
            'title': '**bold title**',
            'slope': '## steep *slope*',
            'version': 'v2',
            'topic_id': '`code`',
            # a normal field that *should* be cooked
            'description': '**cooked**',
        }
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 200

        result = r.json()
        # NOT_MARKDOWN_PROPERTY values must be returned verbatim
        assert result['lang'] == 'fr'
        assert result['title'] == '**bold title**'
        assert result['slope'] == '## steep *slope*'
        assert result['version'] == 'v2'
        assert result['topic_id'] == '`code`'
        # description IS cooked
        assert '<strong>' in result['description']
        assert result['description'] != '**cooked**'

    # ── input-validation hardening ───────────────────────────────

    def test_body_not_object(self):
        r = self.client.post(
            '/v2/cooker',
            content='"just a string"',
            headers={'Content-Type': 'application/json'},
        )
        assert r.status_code == 400

    def test_body_array(self):
        r = self.client.post('/v2/cooker', json=['a', 'b'])
        assert r.status_code == 400

    def test_too_many_keys(self):
        body = {f'key_{i}': 'value' for i in range(16)}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any('Too many keys' in e.get('description', '') for e in errors)

    def test_max_keys_accepted(self):
        body = {f'key_{i}': 'value' for i in range(15)}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 200

    def test_value_too_long(self):
        body = {'description': 'x' * 10_001}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any('exceeds maximum length' in e.get('description', '') for e in errors)

    def test_max_value_length_accepted(self):
        body = {'description': 'x' * 10_000}
        r = self.client.post('/v2/cooker', json=body)
        assert r.status_code == 200

    def test_invalid_json(self):
        r = self.client.post(
            '/v2/cooker',
            content='not json at all',
            headers={'Content-Type': 'application/json'},
        )
        assert r.status_code == 400
