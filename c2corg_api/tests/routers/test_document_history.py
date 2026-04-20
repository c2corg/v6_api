"""
Tests for the FastAPI document-history router
(``/v2/document/{id}/history/{lang}``).
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestDocumentHistoryRouter(BaseTestCase):
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

    def _add_test_data(self):
        contributor_id = global_userids['contributor']

        self.waypoint = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles',
                )
            ],
        )
        self.session.add(self.waypoint)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint, contributor_id)
        self.session.flush()

    def test_get_history(self):
        doc_id = self.waypoint.document_id
        response = self.client.get('/v2/document/{}/history/fr'.format(doc_id))
        assert response.status_code == 200
        body = response.json()

        assert 'title' in body
        assert body['title'] == 'Dent de Crolles'
        assert 'versions' in body
        assert len(body['versions']) > 0

    def test_get_history_no_locale(self):
        doc_id = self.waypoint.document_id
        response = self.client.get('/v2/document/{}/history/en'.format(doc_id))
        assert response.status_code == 404

    def test_get_history_invalid_lang(self):
        doc_id = self.waypoint.document_id
        response = self.client.get('/v2/document/{}/history/zz'.format(doc_id))
        assert response.status_code == 400

    def test_get_history_non_existing_document(self):
        response = self.client.get('/v2/document/9999999/history/fr')
        assert response.status_code == 404
