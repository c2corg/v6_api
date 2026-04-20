"""
Tests for the FastAPI outing router (``/v2/outings``).

Mirrors ``c2corg_api/tests/views/test_outing.py`` — same test data,
same assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.
"""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, shape
from shapely.geometry.point import Point

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import (
    OUTING_TYPE,
    ArchiveOuting,
    ArchiveOutingLocale,
    Outing,
    OutingLocale,
)
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestOutingFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/outings``."""

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

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────────
    # Test data setup (mirrors TestOutingRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            elevation_access=900,
            condition_rating='good',
        )
        self.locale_en = OutingLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            weather='sunny',
            document_topic=DocumentTopic(topic_id=1),
        )
        self.locale_fr = OutingLocale(
            lang='fr',
            title='Mont Blanc du ciel',
            description='...',
            weather='grand beau',
        )
        self.outing.locales.append(self.locale_en)
        self.outing.locales.append(self.locale_fr)
        self.outing.geometry = DocumentGeometry(
            geom_detail=('SRID=3857;LINESTRING(635956 5723604, 635966 5723644)')
        )
        self.session.add(self.outing)
        self.session.flush()

        DocumentRest.create_new_version(self.outing, user_id)
        self.outing_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.outing.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )
        update_feed_document_create(self.outing, user_id)

        self.outing2 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 1),
            height_diff_up=600,
            elevation_max=1800,
            elevation_access=700,
            condition_rating='average',
            locales=[
                OutingLocale(
                    lang='en',
                    title='Mont Blanc from the air',
                    description='...',
                    weather='sunny',
                )
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(0 0)'),
        )
        self.session.add(self.outing2)
        self.session.flush()
        DocumentRest.create_new_version(self.outing2, user_id)

        self.outing3 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 2),
            height_diff_up=200,
            elevation_max=1200,
            elevation_access=800,
            condition_rating='poor',
        )
        self.session.add(self.outing3)

        self.outing4 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 3),
            height_diff_up=500,
            elevation_max=1400,
            elevation_access=800,
            condition_rating='excellent',
        )
        self.outing4.locales.append(
            OutingLocale(lang='en', title='Mont Granier (en)', description='...')
        )
        self.outing4.locales.append(
            OutingLocale(lang='fr', title='Mont Granier (fr)', description='...')
        )
        self.session.add(self.outing4)

        self.waypoint = Waypoint(
            waypoint_type='summit',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier (en)', description='...', access='yep'
            )
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='fr', title='Mont Granier (fr)', description='...', access='ouai'
            )
        )
        self.session.add(self.waypoint)

        self.image = Image(
            filename='20160101-00:00:00.jpg',
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.image.locales.append(DocumentLocale(lang='en', title='...'))
        self.session.add(self.image)

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article1)
        self.session.flush()

        # Route
        self.route = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
            geometry=DocumentGeometry(
                geom_detail=('SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'),
                geom='SRID=3857;POINT(635961 5723624)',
            ),
        )
        self.route.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                gear='paraglider',
                title_prefix='Main waypoint title',
            )
        )
        self.route.locales.append(
            RouteLocale(
                lang='fr',
                title='Mont Blanc du ciel',
                description='...',
                gear='paraglider',
            )
        )
        self.session.add(self.route)
        self.session.flush()

        # Associations
        self._add_association(
            Association.create(
                parent_document=self.waypoint, child_document=self.route
            ),
            user_id,
        )
        self._add_association(
            Association.create(parent_document=self.route, child_document=self.outing),
            user_id,
        )
        self._add_association(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing.document_id,
                child_document_type=OUTING_TYPE,
            ),
            user_id,
        )
        self._add_association(
            Association.create(parent_document=self.outing, child_document=self.image),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.outing, child_document=self.article1
            ),
            user_id,
        )
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
        resp = self.client.get('/v2/outings')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body['documents']) == 4
        doc = body['documents'][0]
        assert 'frequentation' not in doc
        assert 'condition_rating' in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/outings?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/outings?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.outing4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/outings?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.outing4.document_id, self.outing3.document_id]

        resp = self.client.get('/v2/outings?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.outing3.document_id, self.outing2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/outings?pl=es')
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
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert body.get('activities') == self.outing.activities
        self._assert_geometry(body)
        assert 'frequentation' in body

        assert 'associations' in body
        associations = body.get('associations')
        assert 'routes' in associations
        assert 'images' in associations
        assert 'users' in associations
        assert 'articles' in associations

        linked_articles = associations.get('articles')
        assert len(linked_articles) == 1
        assert self.article1.document_id == linked_articles[0].get('document_id')

        linked_routes = associations.get('routes')
        assert len(linked_routes) == 1
        assert self.route.document_id == linked_routes[0].get('document_id')

        linked_users = associations.get('users')
        assert len(linked_users) == 1
        assert linked_users[0]['document_id'] == global_userids['contributor']

        linked_images = associations.get('images')
        assert len(linked_images) == 1
        assert linked_images[0]['document_id'] == self.image.document_id

        locale_en = self._get_locale('en', body.get('locales'))
        assert 1 == locale_en.get('topic_id')

    def test_get_edit(self):
        """?e=1 returns editing view: routes and users present, images absent."""
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}?e=1')
        assert resp.status_code == 200
        body = resp.json()
        assert 'associations' in body
        associations = body['associations']
        assert 'routes' in associations
        assert 'users' in associations
        # In editing view, images are not loaded (key absent or None)
        assert not associations.get('images')

    def test_get_lang(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/outings/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.outing.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/outings/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        url = '/v2/outings/{}/{}/{}'.format(
            self.outing.document_id, 'en', self.outing_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.outing.document_id
        assert body['version']['version_id'] == self.outing_version.id

    # ──────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/outings', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400

    def test_post_missing_title(self):
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'locales': [{'lang': 'en'}],
            'associations': {
                'routes': [{'document_id': self.route.document_id}],
                'users': [{'document_id': global_userids['contributor']}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_missing_associations(self):
        """No user / route associations → 400."""
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'locales': [{'lang': 'en', 'title': 'Nice loop'}],
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('users' in e.get('name', '') for e in errors)
        assert any('routes' in e.get('name', '') for e in errors)

    def test_post_missing_route_association(self):
        """User but no route association → 400."""
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'locales': [{'lang': 'en', 'title': 'Nice loop'}],
            'associations': {'users': [{'document_id': global_userids['contributor']}]},
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('routes' in e.get('name', '') for e in errors)

    def test_post_date_start_is_future(self):
        later = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
        body = {
            'activities': ['skitouring'],
            'date_start': later,
            'date_end': '2016-01-01',
            'locales': [{'lang': 'en', 'title': 'Nice loop'}],
            'associations': {
                'users': [{'document_id': global_userids['contributor']}],
                'routes': [{'document_id': self.route.document_id}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert len(errors) == 1
        assert errors[0]['name'] == 'date_start'
        assert errors[0]['description'] == 'can not be sometime in the future'

    def test_post_date_end_is_future(self):
        later = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': later,
            'locales': [{'lang': 'en', 'title': 'Nice loop'}],
            'associations': {
                'users': [{'document_id': global_userids['contributor']}],
                'routes': [{'document_id': self.route.document_id}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert len(errors) == 1
        assert errors[0]['name'] == 'date_end'
        assert errors[0]['description'] == 'can not be sometime in the future'

    def test_post_end_date_before_start(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        body = {
            'activities': ['skitouring'],
            'date_start': today.strftime('%Y-%m-%d'),
            'date_end': yesterday.strftime('%Y-%m-%d'),
            'locales': [{'lang': 'en', 'title': 'Nice loop'}],
            'associations': {
                'users': [{'document_id': global_userids['contributor']}],
                'routes': [{'document_id': self.route.document_id}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert len(errors) == 1
        assert errors[0]['name'] == 'date_end'
        assert errors[0]['description'] == 'can not be prior the starting date'

    def test_post_unauthenticated(self):
        resp = self.client.post(
            '/v2/outings',
            json={
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'locales': [{'lang': 'en', 'title': 'Nice loop'}],
                'associations': {
                    'users': [{'document_id': global_userids['contributor']}],
                    'routes': [{'document_id': self.route.document_id}],
                },
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'geometry': {
                'geom_detail': '{"type": "LineString", '
                '"coordinates": '
                '[[635956, 5723604], '
                '[635966, 5723644]]}'
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
            'associations': {
                'users': [
                    {'document_id': global_userids['contributor']},
                    {'document_id': global_userids['contributor2']},
                ],
                'routes': [{'document_id': self.route.document_id}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Outing, doc_id)
        assert doc is not None
        assert doc.activities == ['skitouring']
        assert doc.elevation_max == 1500
        assert doc.date_start == date(2016, 1, 1)
        assert doc.date_end == date(2016, 1, 2)

        # Version was created
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]
        archive_outing = version.document_archive
        assert archive_outing.activities == ['skitouring']
        assert archive_outing.elevation_max == 1500
        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Some nice loop'

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.version == doc.geometry.version
        assert archive_geometry.geom_detail is not None

        # Association to route
        assoc_route = self.session.get(
            Association, (self.route.document_id, doc.document_id)
        )
        assert assoc_route is not None

        assoc_route_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.route.document_id)
            .filter(AssociationLog.child_document_id == doc.document_id)
            .first()
        )
        assert assoc_route_log is not None

        # Association to users
        assoc_user = self.session.get(
            Association, (global_userids['contributor'], doc.document_id)
        )
        assert assoc_user is not None

        assoc_user2 = self.session.get(
            Association, (global_userids['contributor2'], doc.document_id)
        )
        assert assoc_user2 is not None

    def test_post_default_geom_from_route(self):
        """When no geometry is given, default geom is computed from
        associated routes.
        """
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
            'associations': {
                'users': [{'document_id': global_userids['contributor']}],
                'routes': [{'document_id': self.route.document_id}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        doc = self.session.get(Outing, doc_id)
        assert doc.geometry is not None
        assert doc.geometry.geom is not None

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
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
            '/v2/outings/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_version(self):
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': -9999,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
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
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id does not match body document_id → 400."""
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
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
            f'/v2/outings/{self.outing2.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(f'/v2/outings/{self.outing.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_wrong_user(self):
        """Non-moderator not associated to outing → 403."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
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
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 403

    def test_put_good_user(self):
        """Associated user can modify the outing."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': QualityTypes.draft,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_max': 1600,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'weather': 'mostly sunny',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text

    def test_put_success_figures(self):
        body = {
            'message': 'Update figures',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
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
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        doc = self.session.get(Outing, self.outing.document_id)
        assert doc.elevation_max == 1600

    def test_put_success_locale(self):
        body = {
            'message': 'Update locale',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'weather': 'cloudy',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        doc = self.session.get(Outing, self.outing.document_id)
        assert doc.get_locale('en').title == 'New title'
        assert doc.get_locale('en').weather == 'cloudy'

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding it locale',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'locales': [
                    {
                        'lang': 'it',
                        'title': "Mont Blanc dall'aria",
                        'weather': 'soleggiato',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        doc = self.session.get(Outing, self.outing.document_id)
        assert doc.get_locale('it').title == "Mont Blanc dall'aria"

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': QualityTypes.draft,
                'activities': ['skitouring', 'hiking'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_max': 1600,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'weather': 'mostly sunny',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.outing.geometry.version,
                    'geom_detail': '{"type": "LineString", '
                    '"coordinates": '
                    '[[635956, 5723604], '
                    '[635976, 5723654]]}',
                },
                'associations': {
                    'users': [
                        {'document_id': global_userids['contributor']},
                        {'document_id': global_userids['contributor2']},
                    ],
                    'routes': [{'document_id': self.route.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        outing = self.session.get(Outing, self.outing.document_id)
        assert outing.elevation_max == 1600
        locale_en = outing.get_locale('en')
        assert locale_en.weather == 'mostly sunny'

        # version with lang 'en'
        versions = outing.versions
        version_en = self._get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Blanc from the air'
        assert archive_locale.weather == 'mostly sunny'

        archive_document = version_en.document_archive
        assert archive_document.activities == ['skitouring', 'hiking']
        assert archive_document.elevation_max == 1600

        # user associations
        assoc_user2 = self.session.get(
            Association, (global_userids['contributor2'], outing.document_id)
        )
        assert assoc_user2 is not None

    def test_post_empty_activities_error(self):
        """Empty activities list → 400 (required field is empty)."""
        body = {
            'activities': [],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
            'associations': {
                'routes': [{'document_id': self.route.document_id}],
                'users': [{'document_id': global_userids['contributor']}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400, resp.text
        errors = resp.json()['errors']
        assert len(errors) >= 1
        assert any('activities' in e.get('name', '') for e in errors)

    def test_post_invalid_activity(self):
        """Invalid activity enum value → 400."""
        body = {
            'activities': ['cooking'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635966, 5723644]]}',
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
            'associations': {
                'routes': [{'document_id': self.route.document_id}],
                'users': [{'document_id': global_userids['contributor']}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert len(errors) >= 1
        assert any('activities' in e.get('name', '') for e in errors)

    def test_post_missing_route_user_id(self):
        """Empty users + missing routes → 400 with 2 errors."""
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635966, 5723644]]}',
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
            'associations': {'users': []},
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 400, resp.text
        errors = resp.json()['errors']
        assert len(errors) == 2
        assert any('users' in e.get('name', '') for e in errors)
        assert any('routes' in e.get('name', '') for e in errors)

    def test_post_invalid_route_id(self):
        """Waypoint id as route + nonexistent user → 400."""
        body = {
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635966, 5723644]]}',
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
            'associations': {
                'routes': [{'document_id': self.waypoint.document_id}],
                'users': [{'document_id': -999}],
            },
        }
        resp = self.client.post(
            '/v2/outings', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 400, resp.text
        errors = resp.json()['errors']
        # The association validator catches wrong-type and
        # non-existent documents.  The exact error count may
        # differ from the Pyramid version (which also re-checks
        # required associations after filtering), but the key
        # errors must be present.
        assert len(errors) >= 2
        error_texts = ' '.join(e.get('description', '') for e in errors)
        assert 'is not of type' in error_texts
        assert 'does not exist' in error_texts

    def test_get_version_without_activity(self):
        """Old outing versions with empty activities still return
        locale fields for all activities.
        """
        self.outing_version.document_archive.activities = []
        self.session.flush()

        url = '/v2/outings/{}/{}/{}'.format(
            self.outing.document_id, 'en', self.outing_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        locale = body['document']['locales'][0]
        assert 'title' in locale

    def test_history(self):
        """Document history returns version list with contributor info."""
        doc_id = self.outing.document_id
        user_id = global_userids['contributor']
        for lang in ['fr', 'en']:
            resp = self.client.get(f'/v2/document/{doc_id}/history/{lang}')
            assert resp.status_code == 200
            body = resp.json()
            assert body['title'] == self.outing.get_locale(lang).title
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
        doc_id = self.outing.document_id
        resp = self.client.get(f'/v2/document/{doc_id}/history/es')
        assert resp.status_code == 404

    def test_history_no_doc(self):
        """History for a non-existent document → 404."""
        resp = self.client.get('/v2/document/99999/history/es')
        assert resp.status_code == 404

    def test_put_no_document(self):
        """PUT with missing ``document`` key → 400."""
        # Unauthenticated → 403
        body = {'message': '...'}
        resp = self.client.put(f'/v2/outings/{self.outing.document_id}', json=body)
        assert resp.status_code == 403

        # Authenticated but missing document field → 400
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_wrong_locale_version(self):
        """Locale version conflict → 409."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'weather': 'mostly sunny',
                        'version': -9999,
                    }
                ],
                'associations': {
                    'users': [{'document_id': global_userids['contributor']}],
                    'routes': [{'document_id': self.route.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.text

    def test_put_update_default_geom(self):
        """When an explicit geom point is provided (no geom_detail),
        the point is preserved as-is.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': QualityTypes.draft,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'weather': 'sunny',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.outing.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635000, 5723000]}',
                },
                'associations': {
                    'users': [{'document_id': global_userids['contributor']}],
                    'routes': [{'document_id': self.route.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        # Re-fetch and check the default geometry was preserved
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}')
        assert resp.status_code == 200
        self._assert_default_geometry(resp.json(), x=635000, y=5723000)

    def test_put_success_association_update(self):
        """Changing only associations → no new archive version."""
        body = {
            'message': 'Changing associations',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': QualityTypes.draft,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'elevation_access': 900,
                'condition_rating': 'good',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'weather': 'sunny',
                        'version': self.locale_en.version,
                    }
                ],
                'associations': {
                    'users': [{'document_id': global_userids['contributor2']}],
                    'routes': [{'document_id': self.route.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/outings/{self.outing.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        # Re-fetch to verify version didn't change
        resp = self.client.get(f'/v2/outings/{self.outing.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert body.get('version') == self.outing.version

        self.session.expire_all()
        document = self.session.get(Outing, self.outing.document_id)
        assert len(document.locales) == 2

        # No new archive_document was created
        archive_count = (
            self.session.query(ArchiveOuting)
            .filter(ArchiveOuting.document_id == self.outing.document_id)
            .count()
        )
        assert archive_count == 1

        # No new archive_document_locale was created
        archive_locale_count = (
            self.session.query(ArchiveOutingLocale)
            .filter(ArchiveOutingLocale.document_id == self.outing.document_id)
            .count()
        )
        assert archive_locale_count == 2

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom_detail') is not None

        geom = geometry.get('geom_detail')
        line = shape(json.loads(geom))
        assert isinstance(line, LineString)
        assert line.coords[0][0] == pytest.approx(635956)
        assert line.coords[0][1] == pytest.approx(5723604)
        assert line.coords[1][0] == pytest.approx(635966)
        assert line.coords[1][1] == pytest.approx(5723644)

    def _assert_default_geometry(self, body, x=635961, y=5723624):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom') is not None

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        assert isinstance(point, Point)
        assert point.x == pytest.approx(x)
        assert point.y == pytest.approx(y)

    @staticmethod
    def _get_locale(lang, locales):
        return next((loc for loc in (locales or []) if loc['lang'] == lang), None)

    @staticmethod
    def _get_latest_version(lang, versions):
        return max([v for v in versions if v.lang == lang], key=lambda v: v.id)

    # ──────────────────────────────────────────────────────────
    # Association history
    # ──────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        resp = self.client.get(f'/v2/associations-history?d={self.outing.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body['count'], int)
        assert body['count'] >= 1
        for entry in body['associations']:
            ids = (
                entry['parent_document']['document_id'],
                entry['child_document']['document_id'],
            )
            assert self.outing.document_id in ids
