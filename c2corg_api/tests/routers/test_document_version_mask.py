"""
Tests for the FastAPI document-version-mask router
(``/v2/versions/mask`` and ``/v2/versions/unmask``).
"""

from fastapi.testclient import TestClient
from sqlalchemy import and_

from c2corg_api.database import get_db
from c2corg_api.models.document import UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class BaseMaskTest(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _add_test_data(self):
        contributor_id = global_userids['contributor']

        self.route = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route')]
        )
        self.session.add(self.route)
        self.session.flush()

        create_new_version(self.route, contributor_id, db=self.session)
        self.session.flush()

        self.route.activities = ['skitouring', 'hiking']
        self.session.flush()

        update_version(
            self.route, contributor_id, 'new version', [UpdateType.FIGURES], []
        )
        self.session.flush()

    def is_masked(self, version_id):
        version = self.session.get(DocumentVersion, version_id)
        self.session.refresh(version)
        assert version is not None
        return version.masked

    def _get_first_version_params(self):
        document_id = self.route.document_id
        lang = 'en'
        (first_version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(
                and_(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.lang == lang,
                )
            )
            .order_by(DocumentVersion.id.asc())
            .first()
        )
        return {
            'document_id': document_id,
            'lang': lang,
            'version_id': first_version_id,
        }

    def _get_version(self, document_id, lang, version_id, username=None):
        """Call GET /v2/routes/{document_id}/{lang}/{version_id}."""
        headers = self._auth_headers(username) if username else {}
        r = self.client.get(
            f'/v2/routes/{document_id}/{lang}/{version_id}', headers=headers
        )
        assert r.status_code == 200
        body = r.json()
        assert 'version' in body
        assert 'masked' in body['version']
        return body


class TestVersionMaskRouter(BaseMaskTest):
    def test_mask_unauthorized(self):
        r = self.client.post('/v2/versions/mask', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/versions/mask', json={}, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    def test_mask_invalid_document_id(self):
        body = {'document_id': -1, 'lang': 'en', 'version_id': 123456}
        r = self.client.post(
            '/v2/versions/mask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400

    def test_mask_invalid_version_id(self):
        document_id = self.route.document_id
        body = {'document_id': document_id, 'lang': 'en', 'version_id': 123456}
        r = self.client.post(
            '/v2/versions/mask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            'Unknown version {}/en/123456'.format(document_id)
            in e.get('description', '')
            for e in errors
        )

    def test_mask_latest_version(self):
        document_id = self.route.document_id
        (latest_version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(
                and_(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.lang == 'en',
                )
            )
            .order_by(DocumentVersion.id.desc())
            .first()
        )
        body = {
            'document_id': document_id,
            'lang': 'en',
            'version_id': latest_version_id,
        }
        r = self.client.post(
            '/v2/versions/mask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any('is the latest one' in e.get('description', '') for e in errors)

    def test_mask(self):
        body = self._get_first_version_params()
        r = self.client.post(
            '/v2/versions/mask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200

        self.session.expire_all()
        assert self.is_masked(body['version_id'])

    def test_not_masked_version(self):
        params = self._get_first_version_params()
        document_id = params['document_id']
        lang = params['lang']
        version_id = params['version_id']

        # anonymous: version is visible with full document payload
        body = self._get_version(document_id, lang, version_id)
        assert not body['version']['masked']
        assert body['document'] is not None
        assert 'skitouring' in body['document'].get('activities', [])

        # authenticated contributor: same behaviour
        body = self._get_version(document_id, lang, version_id, 'contributor')
        assert not body['version']['masked']
        assert body['document'] is not None
        assert 'skitouring' in body['document'].get('activities', [])

    def test_masked_version(self):
        params = self._get_first_version_params()
        document_id = params['document_id']
        lang = params['lang']
        version_id = params['version_id']

        # mask the first version via the API
        r = self.client.post(
            '/v2/versions/mask', json=params, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert self.is_masked(version_id)

        # check masked flag appears in document history
        r = self.client.get(f'/v2/document/{document_id}/history/{lang}')
        assert r.status_code == 200
        versions = r.json()['versions']
        for v in versions:
            assert v['masked'] == (v['version_id'] == version_id)

        # anonymous: document payload is None for masked version
        body = self._get_version(document_id, lang, version_id)
        assert body['version']['masked']
        assert body['document'] is None

        # authenticated contributor (non-moderator): document also hidden
        body = self._get_version(document_id, lang, version_id, 'contributor')
        assert body['version']['masked']
        assert body['document'] is None

        # moderator: full document payload still returned
        body = self._get_version(document_id, lang, version_id, 'moderator')
        assert body['version']['masked']
        assert body['document'] is not None
        assert 'skitouring' in body['document'].get('activities', [])

    def test_updated_cache(self):
        params = self._get_first_version_params()
        document_id = params['document_id']
        lang = params['lang']
        version_id = params['version_id']

        # before masking: history shows unmasked, version endpoint shows document
        r = self.client.get(f'/v2/document/{document_id}/history/{lang}')
        assert r.status_code == 200
        assert not r.json()['versions'][0]['masked']

        body = self._get_version(document_id, lang, version_id, 'contributor')
        assert not body['version']['masked']
        assert body['document'] is not None

        # mask the version
        r = self.client.post(
            '/v2/versions/mask', json=params, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()

        # after masking: history shows masked flag updated
        r = self.client.get(f'/v2/document/{document_id}/history/{lang}')
        assert r.status_code == 200
        assert r.json()['versions'][0]['masked']

        # version endpoint now hides document for non-moderator
        body = self._get_version(document_id, lang, version_id, 'contributor')
        assert body['version']['masked']
        assert body['document'] is None


class TestVersionUnmaskRouter(BaseMaskTest):
    def test_unmask_unauthorized(self):
        r = self.client.post('/v2/versions/unmask', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/versions/unmask', json={}, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    def test_unmask(self):
        body = self._get_first_version_params()
        version_id = body['version_id']

        # first mask it via the API
        r = self.client.post(
            '/v2/versions/mask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert self.is_masked(version_id)

        # then unmask it
        r = self.client.post(
            '/v2/versions/unmask', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert not self.is_masked(version_id)
