"""
Tests for the FastAPI area router (``/v2/areas``).

Mirrors ``c2corg_api/tests/views/test_area.py`` — same test data, same
assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.
"""

import json

from dogpile.cache.api import NO_VALUE
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, shape

from c2corg_api.caching import cache_document_detail
from c2corg_api.database import get_db
from c2corg_api.models.area import AREA_TYPE, Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestAreaFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/areas``.

    Mirrors ``TestAreaRest`` from ``tests/views/test_area.py``.
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
    # Test data setup (mirrors TestAreaRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.area1 = Area(area_type='range')

        self.locale_en = DocumentLocale(lang='en', title='Chartreuse')
        self.locale_fr = DocumentLocale(lang='fr', title='Chartreuse')

        self.area1.locales.append(self.locale_en)
        self.area1.locales.append(self.locale_fr)

        self.area1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
        )

        self.session.add(self.area1)
        self.session.flush()

        DocumentRest.create_new_version(self.area1, user_id)

        self.area1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.area1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.area2 = Area(area_type='range')
        self.session.add(self.area2)
        self.area3 = Area(area_type='range')
        self.session.add(self.area3)
        self.area4 = Area(area_type='admin_limits')
        self.area4.locales.append(DocumentLocale(lang='en', title='Isère'))
        self.area4.locales.append(DocumentLocale(lang='fr', title='Isère'))
        self.session.add(self.area4)

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
        self.session.add(AreaAssociation(document=self.waypoint2, area=self.area1))

        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air', description='...'
                )
            ],
        )

        self.session.add(self.image)
        self.session.flush()

        self._add_association(Association.create(self.area1, self.image), user_id)
        self.session.flush()

        # Force SQLAlchemy to reload geometry from DB as WKBElement
        self.session.expire_all()

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/areas')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        assert 'areas' not in doc
        assert 'geometry' not in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/areas?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/areas?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.area4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/areas?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.area4.document_id, self.area3.document_id]

        resp = self.client.get('/v2/areas?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.area3.document_id, self.area2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/areas?pl=es')
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
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        self._assert_geometry(body)
        assert 'maps' not in body

        assert 'associations' in body
        associations = body.get('associations')
        assert 'images' in associations
        images = associations.get('images')
        assert 1 == len(images)
        assert images[0].get('document_id') == self.image.document_id

    def test_get_lang(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/areas/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.area1.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/areas/{self.area1.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/areas/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        assert self.area1_version is not None
        assert self.area1_version.id is not None
        url = '/v2/areas/{}/{}/{}'.format(
            self.area1.document_id, 'en', self.area1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.area1.document_id
        assert body['version']['version_id'] == self.area1_version.id

    # ──────────────────────────────────────────────────────────────
    # POST (create — moderator only)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/areas', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        assert len(errors) >= 1

    def test_post_missing_title(self):
        body_post = {
            'area_type': 'range',
            'geometry': {
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/areas', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_forbidden_non_moderator(self):
        """Non-moderator POST → 403."""
        body = {
            'area_type': 'range',
            'geometry': {
                'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
        }
        resp = self.client.post(
            '/v2/areas', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 403

    def test_post_unauthenticated(self):
        resp = self.client.post(
            '/v2/areas',
            json={
                'area_type': 'range',
                'geometry': {
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}'  # noqa
                },
                'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
        body = {
            'area_type': 'range',
            'geometry': {
                'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
            'associations': {'images': [{'document_id': self.image.document_id}]},
        }
        resp = self.client.post(
            '/v2/areas', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Area, doc_id)
        assert doc is not None
        assert doc is not None
        assert doc.area_type == 'range'
        assert len(doc.locales) == 1
        assert doc.locales[0].title == 'Chartreuse'
        assert doc.geometry is not None
        assert doc.geometry.geom_detail is not None

        # Version was created
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]
        archive_area = version.document_archive
        assert archive_area.area_type == 'range'
        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Chartreuse'

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.version == doc.geometry.version
        assert archive_geometry.geom_detail is not None

        # Check that links for intersecting documents are created
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.area_id == doc.document_id)
            .all()
        )
        assert len(links) == 2
        link_doc_ids = sorted([lnk.document_id for lnk in links])
        expected = sorted([self.waypoint1.document_id, self.route.document_id])
        assert link_doc_ids == expected

        # Check that a link to the provided image is created
        association_image = self.session.get(
            Association, (doc.document_id, self.image.document_id)
        )
        assert association_image is not None

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Chartreuse',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/areas/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_version(self):
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': -9999,
                'area_type': 'range',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Chartreuse',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id does not match body document_id → 400."""
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Chartreuse',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/areas/{self.area4.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Chartreuse',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(f'/v2/areas/{self.area1.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_update_geometry_fail(self):
        """Non-moderator cannot change geometry → 400."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'geometry': {
                    'version': self.area1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
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
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body['status'] == 'error'
        assert any(
            'No permission to change the geometry' in e.get('description', '')
            for e in body['errors']
        )

    def test_put_success_figures(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
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
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        area = self.session.get(Area, self.area1.document_id)
        assert area is not None
        assert area.area_type == 'admin_limits'
        locale_en = area.get_locale('en')
        assert locale_en is not None
        assert locale_en.title == 'New title'

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'quality': QualityTypes.draft,
                'locales': [{'lang': 'es', 'title': 'Chartreuse'}],
            },
        }
        resp = self.client.put(
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        area = self.session.get(Area, self.area1.document_id)
        assert area is not None
        assert area.get_locale('es').title == 'Chartreuse'  # type: ignore

    def test_put_success_geometry_as_moderator(self):
        """Moderator can change geometry; area associations are updated."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'quality': QualityTypes.draft,
                'geometry': {
                    'version': self.area1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
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
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        area = self.session.get(Area, self.area1.document_id)
        assert area is not None
        assert area.area_type == 'admin_limits'

        # Check that the links to intersecting documents are updated
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.area_id == self.area1.document_id)
            .all()
        )
        assert len(links) == 2
        link_doc_ids = sorted([lnk.document_id for lnk in links])
        expected = sorted([self.waypoint1.document_id, self.route.document_id])
        assert link_doc_ids == expected

    # ──────────────────────────────────────────────────────────────
    # GET associations history
    # ──────────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        """GET /v2/associations-history?d={id} returns association logs."""
        r = self.client.get(f'/v2/associations-history?d={self.area1.document_id}')
        assert r.status_code == 200
        body = r.json()
        assert 'count' in body
        assert 'associations' in body
        assert body['count'] >= 1

        for log in body['associations']:
            assert 'written_at' in log
            assert 'is_creation' in log
            assert 'user' in log
            assert 'child_document' in log
            assert 'parent_document' in log
            child_id = log['child_document']['document_id']
            parent_id = log['parent_document']['document_id']
            assert (
                child_id == self.area1.document_id
                or parent_id == self.area1.document_id
            )

    # ──────────────────────────────────────────────────────────────
    # GET detail — caching
    # ──────────────────────────────────────────────────────────────

    def test_get_caching(self):
        """GET /v2/areas/{id} populates the dogpile cache and serves
        from it on subsequent requests."""
        cache_key = get_cache_key(self.area1.document_id, None, document_type=AREA_TYPE)
        assert cache_key is not None

        # Initially empty
        assert cache_document_detail.get(cache_key) == NO_VALUE

        # First request populates the cache
        r = self.client.get(f'/v2/areas/{self.area1.document_id}')
        assert r.status_code == 200

        assert cache_document_detail.get(cache_key) != NO_VALUE

    # ──────────────────────────────────────────────────────────────
    # POST — non-whitelisted attribute ignored
    # ──────────────────────────────────────────────────────────────

    def test_post_non_whitelisted_attribute(self):
        """``protected=True`` in a POST body is silently ignored."""
        body = {
            'area_type': 'range',
            'protected': True,
            'geometry': {
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
        }
        resp = self.client.post(
            '/v2/areas', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text

        doc_id = resp.json()['document_id']
        document = self.session.get(Area, doc_id)
        assert document is not None
        # protected should have been ignored
        assert not document.protected

    # ──────────────────────────────────────────────────────────────
    # PUT — no document key
    # ──────────────────────────────────────────────────────────────

    def test_put_no_document(self):
        """PUT with body missing the ``document`` key → 400."""
        body = {'message': '...'}
        resp = self.client.put(
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    # ──────────────────────────────────────────────────────────────
    # PUT — success all (figures + locale)
    # ──────────────────────────────────────────────────────────────

    def test_put_success_all(self):
        """Update both figures and locale in one PUT."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
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
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        area = self.session.get(Area, self.area1.document_id)
        assert area is not None
        assert area.area_type == 'admin_limits'
        locale_en = area.get_locale('en')
        assert locale_en is not None
        assert locale_en.title == 'New title'

        # A new version was created for 'en'
        versions = area.versions
        version_en = self._get_latest_version('en', versions)
        assert version_en is not None
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'New title'
        archive_doc = version_en.document_archive
        assert archive_doc.area_type == 'admin_limits'

        # 'fr' locale unchanged
        version_fr = self._get_latest_version('fr', versions)
        assert version_fr is not None
        assert version_fr.document_locales_archive.title == 'Chartreuse'

    # ──────────────────────────────────────────────────────────────
    # PUT — success locale only
    # ──────────────────────────────────────────────────────────────

    def test_put_success_lang_only(self):
        """Update only a locale, figures unchanged."""
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
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
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        area = self.session.get(Area, self.area1.document_id)
        assert area is not None
        assert area.get_locale('en').title == 'New title'

        # Geometry unchanged → area-association links unchanged
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.area_id == self.area1.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].document_id == self.waypoint2.document_id

    # ──────────────────────────────────────────────────────────────
    # PUT — wrong locale version
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_locale_version(self):
        """PUT with a stale locale version → 409 Conflict."""
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [{'lang': 'en', 'title': 'Chartreuse', 'version': -9999}],
            }
        }
        resp = self.client.put(
            f'/v2/areas/{self.area1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_latest_version(lang, versions):
        versions_in_lang = [v for v in versions if v.lang == lang]
        versions_in_lang.sort(key=lambda v: v.id, reverse=True)
        return versions_in_lang[0] if versions_in_lang else None

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom_detail') is not None

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        assert isinstance(polygon, Polygon)
