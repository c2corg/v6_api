"""
Tests for the FastAPI topo-map router (``/v2/maps``).

Mirrors ``c2corg_api/tests/views/test_topo_map.py`` — same test data,
same assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.
"""

import json

from fastapi.testclient import TestClient
from shapely.geometry import Polygon, shape

from c2corg_api.database import get_db
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.route import Route
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestTopoMapFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/maps``.

    Mirrors ``TestTopoMapRest`` from ``tests/views/test_topo_map.py``.
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
    # Test data setup
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.map1 = TopoMap(editor='IGN', scale='25000', code='3431OT')

        self.locale_en = DocumentLocale(lang='en', title="Lac d'Annecy")
        self.locale_fr = DocumentLocale(lang='fr', title="Lac d'Annecy")

        self.map1.locales.append(self.locale_en)
        self.map1.locales.append(self.locale_fr)

        self.map1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774 5706934,611774 5744215,'
            '642834 5744215,642834 5706934,611774 5706934))'
        )

        self.session.add(self.map1)
        self.session.flush()

        DocumentRest.create_new_version(self.map1, user_id)

        self.map1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.map1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.map2 = TopoMap(editor='IGN', scale='25000', code='3432OT')
        self.session.add(self.map2)
        self.map3 = TopoMap(editor='IGN', scale='25000', code='3433OT')
        self.session.add(self.map3)
        self.map4 = TopoMap(editor='IGN', scale='25000', code='3434OT')
        self.map4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.map4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        self.session.add(self.map4)
        self.session.flush()

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
            ),
        )
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(693666.031687976 5741108.7574713)'
            ),
        )
        route_geom = 'SRID=3857;LINESTRING(668518 5728802, 668528 5728812)'
        self.route = Route(
            activities=['skitouring'], geometry=DocumentGeometry(geom_detail=route_geom)
        )

        self.session.add_all([self.waypoint1, self.waypoint2, self.route])
        self.session.add(
            TopoMapAssociation(document=self.waypoint2, topo_map=self.map1)
        )
        self.session.flush()
        self.session.expire_all()

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/maps')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'documents' in body
        assert 'total' in body
        assert body['total'] >= 1
        doc = body['documents'][0]
        assert 'geometry' not in doc

    def test_get_collection_paginated(self):
        body = self.client.get('/v2/maps?offset=0&limit=0').json()
        assert len(body['documents']) == 0
        assert body['total'] == 4

        body = self.client.get('/v2/maps?offset=0&limit=1').json()
        assert len(body['documents']) == 1
        assert body['total'] == 4

        body = self.client.get('/v2/maps?offset=0&limit=2').json()
        assert len(body['documents']) == 2
        assert body['total'] == 4

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/maps?pl=en')
        assert resp.status_code == 200
        body = resp.json()
        for doc in body.get('documents', []):
            locales = doc.get('locales', [])
            if locales:
                assert len(locales) == 1
                assert locales[0]['lang'] == 'en'

    # ──────────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────────

    def test_get(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self._assert_geometry(body)
        # Topo maps should not have their own maps associations populated
        assert 'maps' not in body

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}?cook=en')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}?cook=it')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_lang(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}?l=en')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locales = body.get('locales', [])
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}?l=it')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locales = body.get('locales', [])
        assert len(locales) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/maps/9999999')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/maps/{self.map1.document_id}/en/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locale = body.get('locales', [{}])[0]
        assert locale.get('lang') == 'en'

    def test_get_info_404(self):
        resp = self.client.get('/v2/maps/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        url = '/v2/maps/{}/{}/{}'.format(
            self.map1.document_id, 'en', self.map1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert body['document']['document_id'] == self.map1.document_id

    # ──────────────────────────────────────────────────────────────
    # POST (create) — moderator only
    # ──────────────────────────────────────────────────────────────

    def test_post_not_moderator(self):
        """Non-moderator → 403."""
        resp = self.client.post(
            '/v2/maps', json={}, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 403

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/maps', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        data = resp.json()
        errors = data['errors']
        assert len(errors) >= 2

    def test_post_missing_title(self):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":'
                '[[[668519,5728802],[668518,5745465],'
                '[689156,5745465],[689156,5728802],'
                '[668519,5728802]]]}',
            },
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/maps', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_unauthenticated(self):
        resp = self.client.post('/v2/maps', json={})
        assert resp.status_code in (401, 403)

    def test_post_success(self):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":'
                '[[[668518.249382151,5728802.39591739],'
                '[668518.249382151,5745465.66808356],'
                '[689156.247019149,5745465.66808356],'
                '[689156.247019149,5728802.39591739],'
                '[668518.249382151,5728802.39591739]]]}',
            },
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        resp = self.client.post(
            '/v2/maps', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        self.session.expire_all()
        doc = self.session.get(TopoMap, doc_id)
        assert doc is not None
        assert doc.editor == 'IGN'
        assert doc.scale == '25000'
        assert doc.code == '3432OT'

        version = doc.versions[0]
        archive_map = version.document_archive
        assert archive_map.editor == 'IGN'
        assert archive_map.scale == '25000'
        assert archive_map.code == '3432OT'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.geom_detail is not None

        # Check that links for intersecting documents are created
        links = (
            self.session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.topo_map_id == doc.document_id)
            .order_by(TopoMapAssociation.document_id)
            .all()
        )
        assert len(links) == 2

    # ──────────────────────────────────────────────────────────────
    # PUT (update) — moderator only
    # ──────────────────────────────────────────────────────────────

    def test_put_not_moderator(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 403

    def test_put_wrong_document_id(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': 9999999,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400, resp.text

    def test_put_wrong_document_version(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': -9999,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_locale_version(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_ids(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        # URL id does not match body document_id → 400
        resp = self.client.put(
            f'/v2/maps/{self.map4.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400, resp.text

    def test_put_no_document(self):
        """PUT without a document body → 400."""
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json={'message': '...'},
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(f'/v2/maps/{self.map1.document_id}', json=body)
        assert resp.status_code in (401, 403)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': QualityTypes.draft,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3433OT',
                'geometry': {
                    'version': self.map1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":'
                    '[[[668519.249382151,5728802.39591739],'
                    '[668518.249382151,5745465.66808356],'
                    '[689156.247019149,5745465.66808356],'
                    '[689156.247019149,5728802.39591739],'
                    '[668519.249382151,5728802.39591739]]]}',
                },
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
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        map1 = self.session.get(TopoMap, self.map1.document_id)
        assert map1.code == '3433OT'

        locale_en = map1.get_locale('en')
        assert locale_en.title == 'New title'

        # version with lang 'en'
        versions = map1.versions
        version_en = self._get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'New title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.scale == '25000'
        assert archive_document_en.code == '3433OT'

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = self._get_latest_version('fr', versions)
        archive_locale_fr = version_fr.document_locales_archive
        assert archive_locale_fr.title == "Lac d'Annecy"

        # check that the links to intersecting documents are updated
        links = (
            self.session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.topo_map_id == self.map1.document_id)
            .all()
        )
        assert len(links) == 2

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': QualityTypes.draft,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3433OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        map1 = self.session.get(TopoMap, self.map1.document_id)
        assert map1.code == '3433OT'

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': QualityTypes.draft,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3431OT',
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
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        map1 = self.session.get(TopoMap, self.map1.document_id)
        assert map1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': QualityTypes.draft,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3431OT',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        resp = self.client.put(
            f'/v2/maps/{self.map1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        map1 = self.session.get(TopoMap, self.map1.document_id)
        assert map1.get_locale('es').title == "Lac d'Annecy"

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
    def _get_latest_version(lang, versions):
        return max([v for v in versions if v.lang == lang], key=lambda v: v.id)
