"""
Tests for the FastAPI document-protect router
(``/v2/documents/protect`` and ``/v2/documents/unprotect``).
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class BaseProtectTest(BaseTestCase):
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

        self.waypoint = Waypoint(waypoint_type='summit', elevation=2203)
        self.locale = WaypointLocale(lang='en', title='Mont Granier', description='...')
        self.waypoint.locales.append(self.locale)
        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint, contributor_id)

        self.waypoint2 = Waypoint(
            protected=True, waypoint_type='summit', elevation=2203
        )
        self.locale2 = WaypointLocale(
            lang='en', title='Mont Granier2', description='...'
        )
        self.waypoint2.locales.append(self.locale2)
        self.waypoint2.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint2)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint2, contributor_id)
        self.session.flush()

    def is_protected(self, document_id):
        document = self.session.get(Document, document_id)
        if document is None:
            raise ValueError('Document not found')
        self.session.refresh(document)
        return document.protected


class TestDocumentProtectRouter(BaseProtectTest):
    def test_protect_unauthorized(self):
        r = self.client.post('/v2/documents/protect', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/documents/protect', json={}, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    def test_protect(self):
        body = {'document_id': self.waypoint.document_id}
        r = self.client.post(
            '/v2/documents/protect', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert self.is_protected(self.waypoint.document_id)

    def test_protect_already_protected(self):
        body = {'document_id': self.waypoint2.document_id}
        r = self.client.post(
            '/v2/documents/protect', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert self.is_protected(self.waypoint2.document_id)

    def test_protect_invalid_document_id(self):
        body = {'document_id': -1}
        r = self.client.post(
            '/v2/documents/protect', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400


class TestDocumentUnprotectRouter(BaseProtectTest):
    def test_unprotect_unauthorized(self):
        r = self.client.post('/v2/documents/unprotect', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/documents/unprotect',
            json={},
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 403

    def test_unprotect(self):
        body = {'document_id': self.waypoint2.document_id}
        r = self.client.post(
            '/v2/documents/unprotect',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert not self.is_protected(self.waypoint2.document_id)

    def test_unprotect_already_unprotected(self):
        body = {'document_id': self.waypoint.document_id}
        r = self.client.post(
            '/v2/documents/unprotect',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert r.status_code == 200
        self.session.expire_all()
        assert not self.is_protected(self.waypoint.document_id)

    def test_unprotect_invalid_document_id(self):
        body = {'document_id': -1}
        r = self.client.post(
            '/v2/documents/unprotect',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert r.status_code == 400
