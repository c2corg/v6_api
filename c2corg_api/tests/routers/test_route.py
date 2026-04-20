"""
Tests for the FastAPI route router (``/v2/routes``).

Mirrors ``c2corg_api/tests/views/test_route.py`` — same test data, same
assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.

Uses ``fastapi.testclient.TestClient`` against the **real** application
built by ``create_app()`` so that middleware (CORS, auth, …) and the
full dependency chain are exercised — ensuring behavioural parity with
the legacy Pyramid stack during the migration.

Only ``get_db`` is overridden so that tests share the
transaction-scoped session from ``BaseTestCase`` (per-test rollback).
Authentication uses the real JWT tokens created by ``setup_package()``.
"""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestRouteFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/routes``.

    Mirrors ``TestRouteRest`` from ``tests/views/test_route.py``.
    Runs against the **real** ``create_app()`` so that CORS,
    authentication, and the full middleware stack are exercised.
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
    # Test data setup (mirrors TestRouteRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.route = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
        )

        self.locale_en = RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            gear='paraglider',
            title_prefix='Main waypoint title',
            document_topic=DocumentTopic(topic_id=1),
        )
        self.locale_fr = RouteLocale(
            lang='fr', title='Mont Blanc du ciel', description='...', gear='paraglider'
        )
        self.route.locales.append(self.locale_en)
        self.route.locales.append(self.locale_fr)

        self.route.geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.session.add(self.route)
        self.session.flush()

        DocumentRest.create_new_version(self.route, user_id)
        self.route_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.route.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article1)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.route, child_document=self.article1
            ),
            user_id,
        )

        self.book1 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book1)
        self.session.flush()
        self._add_association(
            Association.create(parent_document=self.book1, child_document=self.route),
            user_id,
        )

        self.route2 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
            locales=[
                RouteLocale(
                    lang='en',
                    title='Mont Blanc from the air',
                    description='...',
                    gear='paraglider',
                ),
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du ciel',
                    description='...',
                    gear='paraglider',
                ),
            ],
        )
        self.session.add(self.route2)
        self.session.flush()
        DocumentRest.create_new_version(self.route2, user_id)

        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=500,
            height_diff_down=500,
            durations=['1'],
            locales=[
                RouteLocale(
                    lang='en',
                    title='Mont Blanc from the air',
                    description='...',
                    gear='paraglider',
                ),
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du ciel',
                    description='...',
                    gear='paraglider',
                ),
            ],
        )
        self.route3.geometry = DocumentGeometry(geom='SRID=3857;POINT(0 0)')
        self.session.add(self.route3)
        self.session.flush()
        DocumentRest.create_new_version(self.route3, user_id)

        self.route4 = Route(
            activities=['rock_climbing'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=500,
            height_diff_down=500,
            durations=['1'],
            climbing_outdoor_type='single',
        )
        self.route4.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                gear='paraglider',
            )
        )
        self.route4.locales.append(
            RouteLocale(
                lang='fr',
                title='Mont Blanc du ciel',
                description='...',
                gear='paraglider',
            )
        )
        self.session.add(self.route4)

        # waypoints
        self.waypoint = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='en',
                title='Mont Granier 1 (en)',
                description='...',
                access='yep',
                access_period='yapa',
            )
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='fr',
                title='Mont Granier 1 (fr)',
                description='...',
                access='ouai',
                access_period='yapa',
            )
        )
        self.session.add(self.waypoint)

        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint2.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier 2 (en)', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint2)

        self.session.flush()

        # associations
        self._add_association(
            Association.create(parent_document=self.route, child_document=self.route4),
            user_id,
        )
        self._add_association(
            Association.create(parent_document=self.route4, child_document=self.route),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.waypoint, child_document=self.route
            ),
            user_id,
        )

        # outings
        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing1)
        self.session.flush()
        self._add_association(
            Association.create(parent_document=self.route, child_document=self.outing1),
            user_id,
        )

        self.outing2 = Outing(
            redirects_to=self.outing1.document_id,
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing2)
        self.session.flush()
        self._add_association(
            Association.create(parent_document=self.route, child_document=self.outing2),
            user_id,
        )

        self.waypoint_tc = Waypoint(
            waypoint_type='access',
            elevation=1776,
            public_transportation_rating='poor service',
            geometry=DocumentGeometry(geom='SRID=3857;POINT(778846 5580167)'),
        )
        self.waypoint_tc.locales.append(
            WaypointLocale(
                lang='fr', title='Roche écroulée', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint_tc)
        self.waypoint_climbing_indoor = Waypoint(
            waypoint_type='climbing_indoor',
            elevation=1,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint_climbing_indoor)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.waypoint_tc, child_document=self.route
            ),
            user_id,
        )
        self.session.flush()

        # Force SQLAlchemy to reload geometry from DB as WKBElement
        # (raw EWKT strings in the identity map would fail Pydantic
        # validation when model_validate reads from_attributes=True).
        self.session.expire_all()

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/routes')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        assert 'height_diff_access' not in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/routes?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/routes?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.route4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/routes?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.route4.document_id, self.route3.document_id]

        resp = self.client.get('/v2/routes?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.route3.document_id, self.route2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/routes?pl=es')
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
        resp = self.client.get(f'/v2/routes/{self.route.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert body.get('activities') == self.route.activities
        assert 'elevation_min' in body
        assert body['glacier_gear'] == 'no'

        locale_en = self._get_locale('en', body.get('locales'))
        assert 'Main waypoint title' == locale_en.get('title_prefix')
        assert 1 == locale_en.get('topic_id')

        assert 'main_waypoint_id' in body
        assert 'associations' in body
        associations = body.get('associations')
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'recent_outings' in associations
        assert 'articles' in associations
        assert 'books' in associations

    def test_get_lang(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/routes/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        url = '/v2/routes/{}/{}/{}'.format(
            self.route.document_id, 'en', self.route_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.route.document_id
        assert body['version']['version_id'] == self.route_version.id

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.route.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/routes/{self.route.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/routes/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/routes', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        assert len(errors) >= 1

    def test_post_missing_title(self):
        body_post = {
            'activities': ['skitouring'],
            'locales': [{'lang': 'en'}],
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post(
            '/v2/routes', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_missing_waypoint_association(self):
        """POST without waypoint associations → 400."""
        body_post = {
            'activities': ['skitouring'],
            'locales': [{'lang': 'en', 'title': 'Test route'}],
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
        }
        resp = self.client.post(
            '/v2/routes', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400

    def test_post_unauthenticated(self):
        resp = self.client.post(
            '/v2/routes',
            json={
                'activities': ['skitouring'],
                'locales': [{'lang': 'en', 'title': 'Test'}],
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'associations': {
                    'waypoints': [{'document_id': self.waypoint.document_id}]
                },
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
        body = {
            'activities': ['skitouring'],
            'elevation_max': 1500,
            'elevation_min': 700,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'glacier_gear': 'no',
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635966, 5723644]]}',
            },
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'gear': 'paraglider',
                }
            ],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post(
            '/v2/routes', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Route, doc_id)
        assert doc is not None
        assert doc.activities == ['skitouring']
        assert doc.elevation_max == 1500

        # Version was created
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]
        archive_route = version.document_archive
        assert archive_route.activities == ['skitouring']
        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Mont Blanc from the air'

        # Association to waypoint
        assoc_wp = self.session.get(
            Association, (self.waypoint.document_id, doc.document_id)
        )
        assert assoc_wp is not None

        assoc_wp_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.child_document_id == doc.document_id)
            .filter(AssociationLog.parent_document_id == self.waypoint.document_id)
            .first()
        )
        assert assoc_wp_log is not None

    def test_post_success_with_main_waypoint(self):
        body = {
            'activities': ['skitouring'],
            'main_waypoint_id': self.waypoint.document_id,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [{'lang': 'en', 'title': 'Route with main wp'}],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post(
            '/v2/routes', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        doc = self.session.get(Route, doc_id)
        assert doc.main_waypoint_id == self.waypoint.document_id

    def test_post_main_waypoint_not_in_associations(self):
        """main_waypoint_id set but no matching association → 400."""
        body = {
            'activities': ['skitouring'],
            'main_waypoint_id': self.waypoint2.document_id,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [{'lang': 'en', 'title': 'Route bad main wp'}],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post(
            '/v2/routes', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/routes/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': -9999,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id does not match body document_id → 400."""
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/routes/{self.route2.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(f'/v2/routes/{self.route.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_success_figures_only(self):
        body = {
            'message': 'Update figures',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_max': 1600,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text
        doc = self.session.get(Route, self.route.document_id)
        assert doc.elevation_max == 1600

    def test_put_success_locale(self):
        body = {
            'message': 'Update locale',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                        'gear': 'new gear',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding it locale',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'it',
                        'title': "Mont Blanc dall'aria",
                        'description': '...',
                        'gear': 'parapendio',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_locale(lang, locales):
        return next((loc for loc in (locales or []) if loc['lang'] == lang), None)

    # ──────────────────────────────────────────────────────────────
    # GET edit view
    # ──────────────────────────────────────────────────────────────

    def test_get_edit(self):
        """?e=1 returns editing view: waypoints + routes, no images/users."""
        resp = self.client.get(f'/v2/routes/{self.route.document_id}?e=1')
        assert resp.status_code == 200
        body = resp.json()
        assert 'associations' in body
        associations = body['associations']
        assert 'waypoints' in associations
        assert 'routes' in associations
        # In editing view, images are not loaded (key absent or None)
        assert not associations.get('images')

    # ──────────────────────────────────────────────────────────────
    # Document history
    # ──────────────────────────────────────────────────────────────

    def test_history(self):
        """Document history returns version list with contributor info."""
        doc_id = self.route.document_id
        user_id = global_userids['contributor']
        for lang in ['fr', 'en']:
            resp = self.client.get(f'/v2/document/{doc_id}/history/{lang}')
            assert resp.status_code == 200
            body = resp.json()
            assert body['title'] == self.route.get_locale(lang).title
            versions = body['versions']
            assert len(versions) == 1
            v = versions[0]
            assert v['name'] == 'Contributor'
            assert 'username' not in v
            assert v['user_id'] == user_id
            assert 'written_at' in v
            assert 'version_id' in v

    def test_history_no_lang(self):
        """History for a lang that has no locale → 404."""
        resp = self.client.get(f'/v2/document/{self.route.document_id}/history/es')
        assert resp.status_code == 404

    def test_history_no_doc(self):
        """History for a non-existent document → 404."""
        resp = self.client.get('/v2/document/99999/history/es')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # POST — additional validation tests
    # ──────────────────────────────────────────────────────────────

    def _post_route_body(self, overrides=None):
        """Return a minimal valid POST body, optionally merged with overrides."""
        body = {
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635961, 5723624]}',
                'geom_detail': (
                    '{"type": "LineString", "coordinates": '
                    '[[635956, 5723604], [635966, 5723644]]}'
                ),
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'gear': 'shoes'}],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        if overrides:
            body.update(overrides)
        return body

    def test_post_empty_activities_and_associations_error(self):
        """Empty activities AND missing waypoint association → errors."""
        body = self._post_route_body({'activities': [], 'associations': {}})
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        descriptions = ' '.join(e.get('description', '') for e in errors)
        assert 'waypoint' in descriptions.lower()

    def test_climing_indoor_waypoint_association(self):
        """A climbing_indoor waypoint cannot be linked to a route."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint_climbing_indoor.document_id,
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint_climbing_indoor.document_id}
                    ]
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        assert any(
            'climbing_indoor' in e.get('description', '')
            or 'climbing_indoor' in e.get('name', '')
            for e in errors
        ), errors

    def test_post_invalid_activity(self):
        """Invalid activity enum value → 400 / 422."""
        body = self._post_route_body({'activities': ['cooking']})
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code in [400, 422], resp.json()

    def test_post_wrong_geom_type(self):
        """Point geometry where LineString is required → 400."""
        body = self._post_route_body(
            {
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                    'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
                }
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        assert any('Invalid geometry' in e.get('description', '') for e in errors), (
            errors
        )

    def test_post_corrupted_geojson_geom(self):
        """Corrupted geometry coordinates → 400."""
        body = self._post_route_body(
            {
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                    'geom_detail': (
                        '{"type": "LineString", "coordinates": '
                        '[[[[[[635956, 5723604, 12345, 67890, 13579]]]]]]}'
                    ),
                }
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        assert any('Invalid geometry' in e.get('description', '') for e in errors), (
            errors
        )

    def test_post_success_3d(self):
        """3D LineString track is accepted and round-trips correctly."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint.document_id,
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635961, 5723624]}',
                    'geom_detail': (
                        '{"type": "LineString", "coordinates": '
                        '[[635956, 5723604, 1200], [635966, 5723644, 1210]]}'
                    ),
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        resp2 = self.client.get(f'/v2/routes/{doc_id}')
        assert resp2.status_code == 200
        geometry = resp2.json()['geometry']
        geom_detail = geometry['geom_detail']
        coords = json.loads(geom_detail)['coordinates']
        assert len(coords) == 2
        assert len(coords[0]) == 3

    def test_post_success_3d_multiline(self):
        """3D MultiLineString track is accepted and round-trips correctly."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint.document_id,
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635961, 5723624]}',
                    'geom_detail': (
                        '{"type": "MultiLineString", "coordinates": '
                        '[[[635956, 5723604, 1200], [635966, 5723644, 1210]]]}'
                    ),
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        resp2 = self.client.get(f'/v2/routes/{doc_id}')
        assert resp2.status_code == 200
        geometry = resp2.json()['geometry']
        geom_detail = geometry['geom_detail']
        coords = json.loads(geom_detail)['coordinates']
        # MultiLineString: list of linestrings
        assert len(coords[0][0]) == 3

    def test_post_success_4d(self):
        """4D LineString track is accepted and round-trips correctly."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint.document_id,
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635961, 5723624]}',
                    'geom_detail': (
                        '{"type": "LineString", "coordinates": '
                        '[[635956, 5723604, 1200, 12345], '
                        '[635966, 5723644, 1210, 12346]]}'
                    ),
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        resp2 = self.client.get(f'/v2/routes/{doc_id}')
        assert resp2.status_code == 200
        geometry = resp2.json()['geometry']
        geom_detail = geometry['geom_detail']
        coords = json.loads(geom_detail)['coordinates']
        assert len(coords[0]) == 4

    def test_post_default_geom_multi_line(self):
        """MultiLineString: default geom (centroid) is set."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint.document_id,
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635966, 5723629]}',
                    'geom_detail': (
                        '{"type": "MultiLineString", "coordinates": '
                        '[[[635956, 5723604], [635966, 5723644]], '
                        '[[635966, 5723614], [635976, 5723654]]]}'
                    ),
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        from c2corg_api.models.route import Route as RouteModel

        self.session.expire_all()
        doc = self.session.get(RouteModel, doc_id)
        assert doc.geometry.geom is not None
        assert doc.geometry.geom_detail is not None

    def test_post_default_geom_from_main_wp(self):
        """No track geometry → default geom taken from main waypoint."""
        body = {
            'activities': ['hiking', 'skitouring'],
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'gear': 'shoes'}],
            'main_waypoint_id': self.waypoint.document_id,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        from c2corg_api.models.route import Route as RouteModel

        self.session.expire_all()
        doc = self.session.get(RouteModel, doc_id)
        assert doc.geometry is not None
        assert doc.geometry.geom is not None
        assert doc.geometry.geom_detail is None

    def test_post_default_geom_from_associated_wps(self):
        """No main waypoint, no track → geom taken from associated waypoints."""
        body = {
            'activities': ['hiking', 'skitouring'],
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'gear': 'shoes'}],
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        from c2corg_api.models.route import Route as RouteModel

        self.session.expire_all()
        doc = self.session.get(RouteModel, doc_id)
        assert doc.geometry is not None
        assert doc.geometry.geom is not None

    def test_post_main_wp_without_association(self):
        """main_waypoint_id set but not in associations → 400."""
        body = self._post_route_body(
            {
                'main_waypoint_id': self.waypoint.document_id,
                'associations': {
                    'waypoints': [{'document_id': self.waypoint2.document_id}]
                },
            }
        )
        resp = self.client.post('/v2/routes', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        assert any(
            'no association to the main waypoint' in e.get('description', '')
            for e in errors
        ), errors

    # ──────────────────────────────────────────────────────────────
    # PUT — additional tests
    # ──────────────────────────────────────────────────────────────

    def test_put_no_document(self):
        """PUT with missing ``document`` key → 400."""
        body = {'message': '...'}
        resp = self.client.put(f'/v2/routes/{self.route.document_id}', json=body)
        assert resp.status_code == 403

        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_success_all(self):
        """Full PUT: update figures, locale, geometry, and associations."""
        from c2corg_api.models.route import Route as RouteModel

        body = {
            'message': 'Update',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_max': 1600,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'gear': 'none',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.route.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635961, 5723629]}',
                    'geom_detail': (
                        '{"type": "LineString", "coordinates": '
                        '[[635956, 5723604], [635976, 5723654]]}'
                    ),
                },
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint.document_id},
                        {'document_id': self.waypoint_tc.document_id},
                    ]
                },
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        route = self.session.get(RouteModel, self.route.document_id)
        assert route.elevation_max == 1600
        assert route.get_locale('en').gear == 'none'

    def test_put_success_new_track_with_default_geom(self):
        """Explicit ``geom`` point alongside a new track: provided geom wins."""
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'gear': 'paraglider',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.route.geometry.version,
                    'geom_detail': (
                        '{"type": "LineString", "coordinates": '
                        '[[635956, 5723604], [635976, 5723654]]}'
                    ),
                    'geom': '{"type": "Point", "coordinates": [635000, 5723000]}',
                },
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint.document_id},
                        {'document_id': self.waypoint_tc.document_id},
                    ]
                },
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        resp2 = self.client.get(f'/v2/routes/{self.route.document_id}')
        assert resp2.status_code == 200
        geom = resp2.json()['geometry']['geom']
        from shapely.geometry import shape

        point = shape(json.loads(geom))
        assert point.x == pytest.approx(635000)
        assert point.y == pytest.approx(5723000)

    def test_put_success_main_wp_changed(self):
        """Changing main_waypoint_id updates title_prefix for all locales."""
        from c2corg_api.models.route import Route as RouteModel

        body = {
            'message': 'Changing main waypoint',
            'document': {
                'document_id': self.route.document_id,
                'main_waypoint_id': self.waypoint2.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'gear': 'paraglider',
                        'version': self.locale_en.version,
                    }
                ],
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint2.document_id},
                        {'document_id': self.waypoint_tc.document_id},
                    ]
                },
            },
        }
        resp = self.client.put(
            f'/v2/routes/{self.route.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        route = self.session.get(RouteModel, self.route.document_id)
        assert route.main_waypoint_id == self.waypoint2.document_id
        locale_en = route.get_locale('en')
        assert locale_en.title_prefix == self.waypoint2.get_locale('en').title
        # check that a link to the new main waypoint is created
        assoc = self.session.get(
            Association, (self.waypoint2.document_id, route.document_id)
        )
        assert assoc is not None

    def test_update_prefix_title(self):
        """check_title_prefix() sets title_prefix from the main waypoint."""
        from c2corg_api.models.route import Route as RouteModel
        from c2corg_api.views.route import check_title_prefix

        self.route.main_waypoint_id = self.waypoint.document_id
        self.session.flush()
        self.session.refresh(self.route)
        check_title_prefix(self.route, create=False)
        self.session.expire_all()

        route = self.session.get(RouteModel, self.route.document_id)
        locale_en = route.get_locale('en')
        assert locale_en.title_prefix == self.waypoint.get_locale('en').title
        locale_fr = route.get_locale('fr')
        assert locale_fr.title_prefix == self.waypoint.get_locale('fr').title

    # ──────────────────────────────────────────────────────────
    # Association history
    # ──────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        resp = self.client.get(f'/v2/associations-history?d={self.route.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body['count'], int)
        assert body['count'] >= 1
        for entry in body['associations']:
            ids = (
                entry['parent_document']['document_id'],
                entry['child_document']['document_id'],
            )
            assert self.route.document_id in ids

    # ──────────────────────────────────────────────────────────
    # Update public transportation rating (moderator endpoint)
    # ──────────────────────────────────────────────────────────

    def test_update_all_routes_forbidden(self):
        """Contributors cannot update all routes."""
        headers = self._auth_headers(username='contributor')
        prefix = '/v2/routes/update_public_transportation_rating'
        resp = self.client.get(prefix, headers=headers)
        assert resp.status_code == 403

    def test_update_all_routes(self):
        """Moderators can trigger the rating update."""
        headers = self._auth_headers(username='moderator')
        prefix = '/v2/routes/update_public_transportation_rating'
        resp = self.client.get(prefix, headers=headers)
        assert resp.status_code == 200
        self.session.flush()
        self.session.refresh(self.route)
        assert self.route.public_transportation_rating == 'poor service'

    def test_update_all_routes_without_extrapolation(self):
        """Moderators can run without waypoint extrapolation."""
        self.route.route_types = ['traverse']
        self.session.flush()
        headers = self._auth_headers(username='moderator')
        prefix = '/v2/routes/update_public_transportation_rating'
        resp = self.client.get(
            prefix + '?waypoint_extrapolation=false', headers=headers
        )
        assert resp.status_code == 200
        self.session.flush()
        self.session.refresh(self.route)
        assert self.route.public_transportation_rating == 'unknown service'
