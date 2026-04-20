"""
Tests for the FastAPI coverage router (``/v2/coverages``).

Mirrors ``c2corg_api/tests/views/test_coverage.py`` — same test data, same
assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.

Coverage has **no archive / wiki-style versioning** and **no info / version
endpoints**, so the test surface is smaller than for other document types.
"""

import json

from dogpile.cache.api import NO_VALUE
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, shape

from c2corg_api.caching import cache_document_detail
from c2corg_api.database import get_db
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.coverage import COVERAGE_TYPE, Coverage
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, settings
from c2corg_api.tests.routers import get_real_app


class TestCoverageFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/coverages``.

    Mirrors ``TestCoverageRest`` from ``tests/views/test_coverage.py``.
    """

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

    # ──────────────────────────────────────────────────────────────
    # Test data setup (mirrors TestCoverageRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        self.coverage1 = Coverage(coverage_type='fr-se')

        self.locale_en = DocumentLocale(lang='en', title='South-East France')
        self.locale_fr = DocumentLocale(lang='fr', title='Sud-Est de la France')

        self.coverage1.locales.append(self.locale_en)
        self.coverage1.locales.append(self.locale_fr)

        self.coverage1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
        )

        self.session.add(self.coverage1)
        self.session.flush()

        # Coverage has no archive model — skip create_new_version

        self.coverage2 = Coverage(coverage_type='fr-nw')
        self.coverage2.locales.append(
            DocumentLocale(lang='en', title='North-West France')
        )
        self.coverage2.locales.append(
            DocumentLocale(lang='fr', title='Nord-Ouest de la France')
        )
        self.session.add(self.coverage2)
        self.session.flush()

        # Force SQLAlchemy to reload geometry from DB as WKBElement
        self.session.expire_all()

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/coverages')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        # coverage2 has no geometry set
        assert doc.get('geometry') is None

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/coverages?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 2

        resp = self.client.get('/v2/coverages?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.coverage2.document_id]
        assert resp.json()['total'] == 2

        resp = self.client.get('/v2/coverages?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.coverage2.document_id, self.coverage1.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/coverages?pl=es')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        locales = doc.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────────

    def test_get(self):
        resp = self.client.get(f'/v2/coverages/{self.coverage1.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        self._assert_geometry(body)

    def test_get_lang(self):
        resp = self.client.get(f'/v2/coverages/{self.coverage1.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/coverages/{self.coverage1.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/coverages/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/coverages/{self.coverage1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/coverages/{self.coverage1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/coverages', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        assert len(errors) >= 1

    def test_post_unauthenticated(self):
        resp = self.client.post(
            '/v2/coverages',
            json={
                'coverage_type': 'fr-ne',
                'geometry': {'geom_detail': self._polygon_geojson()},
                'locales': [{'lang': 'en', 'title': 'North-East France'}],
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
        body = {
            'coverage_type': 'fr-ne',
            'geometry': {'geom_detail': self._polygon_geojson()},
            'locales': [{'lang': 'en', 'title': 'North-East France'}],
        }
        resp = self.client.post(
            '/v2/coverages', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Coverage, doc_id)
        assert doc is not None
        assert doc.coverage_type == 'fr-ne'
        assert len(doc.locales) == 1
        assert doc.locales[0].title == 'North-East France'
        assert doc.geometry is not None
        assert doc.geometry.geom_detail is not None

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/coverages/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_version(self):
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': -9999,
                'coverage_type': 'fr-se',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id does not match body document_id → 400."""
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage2.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(f'/v2/coverages/{self.coverage1.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_success_figures(self):
        body = {
            'message': 'Update figures',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-nw',
                'quality': QualityTypes.draft,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        assert coverage.coverage_type == 'fr-nw'

    def test_put_success_lang(self):
        body = {
            'message': 'Update lang',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': QualityTypes.draft,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        assert coverage.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': QualityTypes.draft,
                'locales': [{'lang': 'es', 'title': 'Sureste de Francia'}],
            },
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        assert coverage.get_locale('es').title == 'Sureste de Francia'

    def test_put_success_geometry(self):
        body = {
            'message': 'Update geometry',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': QualityTypes.draft,
                'geometry': {
                    'version': self.coverage1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":'
                    '[[[668520.0,5728802.0],'
                    '[668520.0,5745465.0],'
                    '[689156.0,5745465.0],'
                    '[689156.0,5728802.0],'
                    '[668520.0,5728802.0]]]}',
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'South-East France',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        assert coverage.geometry.geom_detail is not None

    # ──────────────────────────────────────────────────────────────
    # GET detail — caching
    # ──────────────────────────────────────────────────────────────

    def test_get_caching(self):
        """GET /v2/coverages/{id} populates the dogpile cache."""
        cache_key = get_cache_key(
            self.coverage1.document_id, None, document_type=COVERAGE_TYPE,
            db=self.session,
        )
        assert cache_document_detail.get(cache_key) == NO_VALUE

        r = self.client.get(f'/v2/coverages/{self.coverage1.document_id}')
        assert r.status_code == 200

        assert cache_document_detail.get(cache_key) != NO_VALUE

    # ──────────────────────────────────────────────────────────────
    # POST — additional validations
    # ──────────────────────────────────────────────────────────────

    def test_post_non_whitelisted_attribute(self):
        """``protected`` is silently ignored on create."""
        body = {
            'coverage_type': 'fr-se',
            'protected': True,
            'geometry': {'geom_detail': self._polygon_geojson()},
            'locales': [{'lang': 'en', 'title': 'South-East France'}],
        }
        resp = self.client.post(
            '/v2/coverages', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200
        doc_id = resp.json()['document_id']
        doc = self.session.get(Coverage, doc_id)
        assert doc is not None
        assert not doc.protected

    def test_post_wrong_geom_type(self):
        """Point instead of Polygon → validation error."""
        body = {
            'coverage_type': 'fr-se',
            'geometry': {
                'geom_detail': ('{"type": "Point", "coordinates": [635956, 5723604]}')
            },
            'locales': [{'lang': 'en', 'title': 'Wrong geom'}],
        }
        resp = self.client.post(
            '/v2/coverages', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        descriptions = [e.get('description', '') for e in errors]
        assert any('Invalid geometry type' in d for d in descriptions), (
            f'Expected geometry type error in {errors}'
        )

    # ──────────────────────────────────────────────────────────────
    # PUT — additional validations
    # ──────────────────────────────────────────────────────────────

    def test_put_no_document(self):
        """Body without ``document`` key → 400."""
        body = {'message': '...'}
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_wrong_locale_version(self):
        """Wrong locale version → 409."""
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {'lang': 'en', 'title': 'South-East France', 'version': -9999}
                ],
            }
        }
        resp = self.client.put(
            f'/v2/coverages/{self.coverage1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom_detail') is not None

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        assert isinstance(polygon, Polygon)

    @staticmethod
    def _polygon_geojson():
        return (
            '{"type":"Polygon","coordinates":'
            '[[[668518.249382151,5728802.39591739],'
            '[668518.249382151,5745465.66808356],'
            '[689156.247019149,5745465.66808356],'
            '[689156.247019149,5728802.39591739],'
            '[668518.249382151,5728802.39591739]]]}'
        )
