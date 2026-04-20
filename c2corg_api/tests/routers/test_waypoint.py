"""
Tests for the FastAPI waypoint router (``/v2/waypoints``).

Mirrors ``c2corg_api/tests/views/test_waypoint.py`` — same test data,
same assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.
"""

import json
from datetime import date

from fastapi.testclient import TestClient
from shapely.geometry import shape
from shapely.geometry.point import Point

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestWaypointFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/waypoints``."""

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
    # Test data setup (mirrors TestWaypointRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint = Waypoint(waypoint_type='summit', elevation=2203)
        self.locale_en = WaypointLocale(
            lang='en',
            title='Mont Granier',
            description='...',
            access='yep',
            document_topic=DocumentTopic(topic_id=1),
        )
        self.locale_fr = WaypointLocale(
            lang='fr', title='Mont Granier', description='...', access='ouai'
        )
        self.waypoint.locales.append(self.locale_en)
        self.waypoint.locales.append(self.locale_fr)
        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint)
        self.session.flush()

        DocumentRest.create_new_version(self.waypoint, user_id)
        self.waypoint_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.waypoint.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )
        update_feed_document_create(self.waypoint, user_id)

        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint2)

        self.waypoint3 = Waypoint(
            waypoint_type='summit',
            elevation=3,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint3)

        self.waypoint4 = Waypoint(
            waypoint_type='summit',
            elevation=4,
            protected=True,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(659775 5694854)'),
        )
        self.waypoint4.locales.append(
            WaypointLocale(
                lang='en',
                title='Mont Granier',
                description='...',
                access='yep',
                external_resources='https://wikipedia.com/en',
            )
        )
        self.waypoint4.locales.append(
            WaypointLocale(
                lang='fr',
                title='Mont Granier',
                description='...',
                access='ouai',
                external_resources='https://wikipedia.com/fr',
            )
        )
        self.session.add(self.waypoint4)

        self.waypoint5 = Waypoint(
            waypoint_type='summit',
            elevation=3,
            redirects_to=self.waypoint.document_id,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint5.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint5)

        self.waypoint6 = Waypoint(
            waypoint_type='access',
            elevation=1096,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(657403 5691411)'),
        )
        self.waypoint6.locales.append(
            WaypointLocale(
                lang='fr', title='La Plagne', description='...', access='ouai'
            )
        )
        self.waypoint6.locales.append(
            WaypointLocale(
                lang='en', title='La Plagne', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint6)

        self.session.flush()

        DocumentRest.create_new_version(self.waypoint4, user_id)
        DocumentRest.create_new_version(self.waypoint5, user_id)
        DocumentRest.create_new_version(self.waypoint6, user_id)

        # Associations
        route1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.route1 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
            main_waypoint_id=self.waypoint.document_id,
            geometry=route1_geometry,
        )
        self.route1.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
            )
        )
        self.session.add(self.route1)
        self.session.flush()

        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
        )
        self.route3.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
            )
        )
        self.session.add(self.route3)
        self.session.flush()

        self._add_association(
            Association.create(
                parent_document=self.waypoint, child_document=self.waypoint4
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.waypoint, child_document=self.route1
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.waypoint4, child_document=self.route3
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.route1, child_document=self.waypoint6
            ),
            user_id,
        )

        # article
        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article1)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.waypoint, child_document=self.article1
            ),
            user_id,
        )

        self.article2 = Article(
            categories=['site_info'],
            activities=['hiking'],
            article_type='personal',
            locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
        )
        self.session.add(self.article2)
        self.session.flush()
        DocumentRest.create_new_version(self.article2, user_id)

        # outings
        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 3),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing1)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.route1, child_document=self.outing1
            ),
            user_id,
        )

        self.outing3 = Outing(
            activities=['skitouring'],
            date_start=date(2015, 12, 31),
            date_end=date(2016, 1, 1),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing3)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.route3, child_document=self.outing3
            ),
            user_id,
        )

        # topo map
        self.topo_map1 = TopoMap(
            code='3232ET',
            editor='IGN',
            scale='25000',
            locales=[DocumentLocale(lang='fr', title='Belley')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            ),
        )
        self.session.add(self.topo_map1)
        self.session.flush()
        self.session.add(
            TopoMapAssociation(document=self.waypoint, topo_map=self.topo_map1)
        )

        # areas
        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            ),
        )
        self.area2 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='France')]
        )
        self.session.add_all([self.area1, self.area2])
        self.session.add(AreaAssociation(document=self.waypoint, area=self.area2))
        self.session.flush()
        self.session.expire_all()

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/waypoints')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'documents' in body
        assert 'total' in body
        assert body['total'] >= 1
        doc = body['documents'][0]
        assert 'waypoint_type' in doc
        assert 'elevation' in doc

    def test_get_collection_paginated(self):
        body = self.client.get('/v2/waypoints?offset=0&limit=0').json()
        assert len(body['documents']) == 0

        body = self.client.get('/v2/waypoints?offset=0&limit=1').json()
        assert len(body['documents']) == 1

        body = self.client.get('/v2/waypoints?offset=0&limit=2').json()
        assert len(body['documents']) == 2

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/waypoints?pl=en')
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
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self._assert_geometry(body)
        assert 'waypoint_type' in body

        assert 'associations' in body
        associations = body.get('associations')
        assert 'articles' in associations

        linked_articles = associations.get('articles')
        assert len(linked_articles) == 1
        assert self.article1.document_id == linked_articles[0].get('document_id')

        # Check maps are included
        assert 'maps' in body
        maps = body.get('maps')
        assert maps is not None
        assert 1 == len(maps)
        topo_map = maps[0]
        assert topo_map.get('code') == '3232ET'

        # Check areas
        assert 'areas' in body

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}?cook=en')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}?cook=it')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'cooked' in body

    def test_get_lang(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}?l=en')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locales = body.get('locales', [])
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}?l=it')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locales = body.get('locales', [])
        assert len(locales) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/waypoints/9999999')
        assert resp.status_code == 404

    def test_get_redirected(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint5.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get('redirects_to') == self.waypoint.document_id
        # available_langs should list all locales of the redirect target
        assert set(body['available_langs']) == {'en', 'fr'}

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}/en/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locale = body.get('locales', [{}])[0]
        assert locale.get('lang') == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}/es/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locale = body.get('locales', [{}])[0]
        assert locale.get('lang') == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/waypoints/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        url = '/v2/waypoints/{}/{}/{}'.format(
            self.waypoint.document_id, 'en', self.waypoint_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert body['document']['document_id'] == self.waypoint.document_id

    # ──────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors."""
        resp = self.client.post('/v2/waypoints', json={}, headers=self._auth_headers())
        assert resp.status_code == 400

    def test_post_missing_title(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_missing_geometry(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('geometry' in e.get('name', '') for e in errors)

    def test_post_missing_geom(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {},
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('geom' in e.get('name', '') for e in errors)

    def test_post_missing_locales(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text

    def test_post_same_locale_twice(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'},
                {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'},
            ],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text

    def test_post_missing_elevation(self):
        body = {
            'waypoint_type': 'summit',
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('elevation' in e.get('name', '') for e in errors)

    def test_post_non_whitelisted_attribute(self):
        """``protected=True`` in POST body is silently ignored by FastAPI/Pydantic."""
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'protected': True,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        from c2corg_api.models.waypoint import Waypoint as _Waypoint  # noqa: PLC0415

        doc = self.session.get(_Waypoint, doc_id)
        assert doc is not None
        assert not doc.protected

    def test_post_empty_assoc_in_new_w_document(self):
        """Posting with all empty association lists (including extra keys
        like 'all_routes' and 'recent_outings' from the view schema) succeeds."""
        body = {
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
            'associations': {
                'waypoints': [],
                'waypoint_children': [],
                'routes': [],
                'users': [],
                'articles': [],
                'images': [],
                'areas': [],
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.text

    def test_post_invalid_waypoint_type(self):
        body = {
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'waypoint_type': 'swimming-pool',
            'elevation': 3779,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert len(errors) >= 1
        assert any('waypoint_type' in e.get('name', '') for e in errors)

    def test_post_unauthenticated(self):
        resp = self.client.post('/v2/waypoints', json={})
        assert resp.status_code in (401, 403)

    def test_post_success(self):
        body = {
            'document_id': 1234,
            'version': 2345,
            'geometry': {
                'document_id': 5678,
                'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {
                    'id': 3456,
                    'version': 4567,
                    'lang': 'en',
                    'title': 'Mont Pourri',
                    'access': 'y',
                }
            ],
            'associations': {
                'waypoint_children': [{'document_id': self.waypoint2.document_id}]
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        self.session.expire_all()
        doc = self.session.get(Waypoint, doc_id)
        assert doc is not None

        # document_id and version were reset
        assert doc_id != 1234
        assert doc.version == 1

        version = doc.versions[0]
        archive_waypoint = version.document_archive
        assert archive_waypoint.waypoint_type == 'summit'
        assert archive_waypoint.elevation == 3779

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Mont Pourri'
        assert archive_locale.access == 'y'

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.geom is not None
        assert archive_geometry.geom_detail is not None

        # Check area link
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.document_id == doc.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].area_id == self.area1.document_id

        # Check map link
        links = (
            self.session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.document_id == doc.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].topo_map_id == self.topo_map1.document_id

        # Check association to child waypoint
        association_wp = self.session.get(
            Association, (doc.document_id, self.waypoint2.document_id)
        )
        assert association_wp is not None

    def test_post_empty_associations(self):
        """Posting with empty association lists → success."""
        body = {
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
            'associations': {
                'waypoints': [],
                'waypoint_children': [],
                'routes': [],
                'users': [],
                'articles': [],
                'images': [],
                'areas': [],
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text

    def test_post_invalid_association_with_redirected_doc(self):
        body = {
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
            'associations': {
                'waypoints': [{'document_id': self.waypoint5.document_id}]
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers('contributor2')
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any(
            'does not exist or is redirected' in e.get('description', '')
            for e in errors
        )

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': 9999999,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'n',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 400, resp.text

    def test_put_wrong_document_version(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': -9999,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'n',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_locale_version(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'n',
                        'version': -9999,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 409, resp.text

    def test_put_wrong_ids(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        # URL id != body document_id (use a non-protected waypoint)
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint2.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 400, resp.text

    def test_put_no_document(self):
        """PUT without a document body → 400."""
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json={'message': '...'},
            headers=self._auth_headers(),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(f'/v2/waypoints/{self.waypoint.document_id}', json=body)
        assert resp.status_code in (401, 403)

    def test_put_missing_elevation(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('elevation' in e.get('name', '') for e in errors)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier!',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.waypoint.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
                },
                'associations': {
                    'waypoint_children': [{'document_id': self.waypoint2.document_id}],
                    'routes': [{'document_id': self.route1.document_id}],
                    'articles': [{'document_id': self.article1.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.elevation == 1234

        locale_en = waypoint.get_locale('en')
        assert locale_en.description == 'A.'
        assert locale_en.access == 'n'

        # version with lang 'en'
        versions = waypoint.versions
        version_en = self._get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Granier!'
        assert archive_locale.access == 'n'

        archive_document_en = version_en.document_archive
        assert archive_document_en.waypoint_type == 'summit'
        assert archive_document_en.elevation == 1234

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = self._get_latest_version('fr', versions)
        archive_locale_fr = version_fr.document_locales_archive
        assert archive_locale_fr.title == 'Mont Granier'
        assert archive_locale_fr.access == 'ouai'

        # Check area links
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.document_id == self.waypoint.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].area_id == self.area1.document_id

        # Check map links
        links = (
            self.session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.document_id == self.waypoint.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].topo_map_id == self.topo_map1.document_id

        # Check association to child waypoint
        association_wp = self.session.get(
            Association, (waypoint.document_id, self.waypoint2.document_id)
        )
        assert association_wp is not None

        # Check association to article
        association_a = self.session.get(
            Association, (waypoint.document_id, self.article1.document_id)
        )
        assert association_a is not None

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'yep',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.elevation == 1234

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'description': '...',
                        'access': 'yep',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {
                        'lang': 'it',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'si',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.get_locale('it').title == 'Mont Granier'
        assert waypoint.get_locale('it').access == 'si'

    # ──────────────────────────────────────────────────────────────
    # GET – additional coverage
    # ──────────────────────────────────────────────────────────────

    def test_get_with_empty_arrays(self):
        """Test-case for https://github.com/c2corg/v6_api/issues/231"""
        assert self.waypoint2.rock_types == []
        resp = self.client.get(f'/v2/waypoints/{self.waypoint2.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'rock_types' in body
        assert body['rock_types'] == []

    def test_get_edit(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint.document_id}?e=1')
        assert resp.status_code == 200, resp.text
        body = resp.json()

        associations = body.get('associations', {})
        # recent_outings should not be populated in editing view
        assert not associations.get('recent_outings')
        assert 'maps' in body
        assert 'areas' not in body
        assert 'associations' in body
        assert 'waypoints' in associations
        assert 'waypoint_children' in associations

    def test_get_with_external_resources(self):
        """Test getting a document with locale and external resources."""
        resp = self.client.get(f'/v2/waypoints/{self.waypoint4.document_id}')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        locales = body.get('locales', [])
        locale_en = next((loc for loc in locales if loc['lang'] == 'en'), None)
        assert locale_en is not None
        assert locale_en.get('external_resources') == 'https://wikipedia.com/en'

    def test_get_info_redirect(self):
        resp = self.client.get(f'/v2/waypoints/{self.waypoint5.document_id}/en/info')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert 'redirects_to' in body
        assert body['redirects_to'] == self.waypoint.document_id
        assert set(body['available_langs']) == {'en', 'fr'}

    def test_get_collection_big_offset(self):
        resp = self.client.get('/v2/waypoints?offset=10000')
        assert resp.status_code == 400, resp.text

        resp = self.client.get('/v2/waypoints?offset=9970&limit=30')
        assert resp.status_code == 200, resp.text

    # ──────────────────────────────────────────────────────────────
    # POST – additional coverage
    # ──────────────────────────────────────────────────────────────

    def test_post_wrong_geom_type(self):
        body = {
            'document_id': 1234,
            'version': 2345,
            'geometry': {
                'document_id': 5678,
                'version': 6789,
                'geom': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635960, 5723610]]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {
                    'id': 3456,
                    'version': 4567,
                    'lang': 'en',
                    'title': 'Mont Pourri',
                    'access': 'y',
                }
            ],
            'associations': {
                'waypoint_children': [{'document_id': self.waypoint2.document_id}]
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any('LINESTRING' in e.get('description', '') for e in errors)

    def test_post_invalid_association_with_personal_article(self):
        body = {
            'document_id': 1234,
            'version': 2345,
            'geometry': {
                'document_id': 5678,
                'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {
                    'id': 3456,
                    'version': 4567,
                    'lang': 'en',
                    'title': 'Mont Pourri',
                    'access': 'y',
                }
            ],
            'associations': {'articles': [{'document_id': self.article2.document_id}]},
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers('contributor2')
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any(
            'no rights to modify associations with article' in e.get('description', '')
            for e in errors
        )

    def test_post_success_external_resource(self):
        """Test creating a document with external resources in locale."""
        external_resources = 'https://wikipedia.com/en'
        body = {
            'geometry': {
                'document_id': 5678,
                'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {
                    'id': 3456,
                    'version': 4567,
                    'lang': 'en',
                    'title': 'Mont Pourri',
                    'access': 'y',
                    'external_resources': external_resources,
                }
            ],
            'associations': {
                'waypoint_children': [{'document_id': self.waypoint2.document_id}]
            },
        }
        resp = self.client.post(
            '/v2/waypoints', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']

        self.session.expire_all()
        doc = self.session.get(Waypoint, doc_id)
        locale_en = doc.get_locale('en')
        assert locale_en.external_resources == external_resources

    # ──────────────────────────────────────────────────────────────
    # PUT – additional coverage
    # ──────────────────────────────────────────────────────────────

    def test_put_success_figures_and_lang_only(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': None,
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.elevation == 1234

        locale_en = waypoint.get_locale('en')
        assert locale_en.description == 'A.'
        assert locale_en.access == 'n'

        # version with lang 'en'
        versions = waypoint.versions
        version_en = self._get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Granier'
        assert archive_locale.access == 'n'

        archive_document_en = version_en.document_archive
        assert archive_document_en.waypoint_type == 'summit'
        assert archive_document_en.elevation == 1234

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 1

        # version with lang 'fr'
        version_fr = self._get_latest_version('fr', versions)
        archive_locale_fr = version_fr.document_locales_archive
        assert archive_locale_fr.title == 'Mont Granier'
        assert archive_locale_fr.access == 'ouai'

        # area links should NOT be updated (geometry did not change)
        links = (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.document_id == self.waypoint.document_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].area_id == self.area2.document_id

    def test_put_boolean_default_values(self):
        """Test-case for https://github.com/c2corg/v6_api/issues/229"""
        assert self.waypoint.blanket_unstaffed is None
        assert self.waypoint.matress_unstaffed is None
        assert self.waypoint.gas_unstaffed is None
        assert self.waypoint.heating_unstaffed is None

        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'blanket_unstaffed': True,
                'matress_unstaffed': False,
                'gas_unstaffed': None,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': '...',
                        'access': 'yep',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        assert waypoint.blanket_unstaffed == True
        assert waypoint.matress_unstaffed == False
        assert waypoint.gas_unstaffed is None
        assert waypoint.heating_unstaffed is None

    def test_put_add_geometry(self):
        """Tests adding a geometry to a waypoint without geometry."""
        # Create a waypoint with no geometry
        waypoint = Waypoint(waypoint_type='summit', elevation=3779)
        locale_en = WaypointLocale(lang='en', title='Mont Pourri', access='y')
        waypoint.locales.append(locale_en)
        self.session.add(waypoint)
        self.session.flush()
        user_id = global_userids['contributor']
        DocumentRest.create_new_version(waypoint, user_id)

        # Then add a geometry
        body = {
            'message': 'Adding geom',
            'document': {
                'document_id': waypoint.document_id,
                'version': waypoint.version,
                'quality': QualityTypes.draft,
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': [],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        document = self.session.get(Waypoint, waypoint.document_id)
        versions = document.versions
        assert len(versions) == 2

        # version with lang 'en'
        version_en = self._get_latest_version('en', versions)
        assert version_en.lang == 'en'

        meta_data_en = version_en.history_metadata
        assert meta_data_en.comment == 'Adding geom'
        assert meta_data_en.written_at is not None

    def test_put_merged_wp(self):
        """Tests updating a waypoint with redirects_to set."""
        body = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint5.document_id,
                'version': self.waypoint5.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': [],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint5.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any(
            'can not update merged document' in e.get('description', '') for e in errors
        )

    def test_put_protected_no_permission(self):
        """Tests updating a protected waypoint as non-moderator."""
        body = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint4.document_id,
                'version': self.waypoint4.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': [],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint4.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 403, resp.text

    def test_put_protected_as_moderator(self):
        """Tests updating a protected waypoint as moderator."""
        body = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint4.document_id,
                'version': self.waypoint4.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': [],
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint4.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

    def test_put_no_permission_for_association_change(self):
        """Test that non-moderator users can not remove associations."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'orientations': None,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier!',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.waypoint.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
                },
                'associations': {
                    'waypoint_children': [
                        # association to waypoint 4 is removed
                    ],
                    'routes': [{'document_id': self.route1.document_id}],
                    'articles': [{'document_id': self.article1.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        errors = data['errors']
        assert any(
            'no rights to modify associations' in e.get('description', '')
            for e in errors
        )

    def test_put_add_new_association(self):
        """Test that non-moderator users can add new associations."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'orientations': None,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier!',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                    }
                ],
                'geometry': {
                    'version': self.waypoint.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
                },
                'associations': {
                    'waypoint_children': [
                        {'document_id': self.waypoint4.document_id},
                        {'document_id': self.waypoint2.document_id},
                    ],
                    'routes': [{'document_id': self.route1.document_id}],
                    'articles': [{'document_id': self.article1.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text

        association = self.session.get(
            Association, (self.waypoint.document_id, self.waypoint2.document_id)
        )
        assert association is not None

    def test_put_success_external_resource(self):
        """Test updating a document by adding external resources."""
        external_resources = 'https://wikipedia.com/en'
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': QualityTypes.draft,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Granier',
                        'description': 'A.',
                        'access': 'n',
                        'version': self.locale_en.version,
                        'external_resources': external_resources,
                    }
                ],
                'geometry': None,
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        waypoint = self.session.get(Waypoint, self.waypoint.document_id)
        locale_en = waypoint.get_locale('en')
        assert locale_en.external_resources == external_resources

    def test_update_access_waypoints_pt(self):
        """Test updating waypoint public transportation rating."""
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint6.document_id,
                'version': self.waypoint6.version,
                'waypoint_type': 'access',
                'elevation': self.waypoint6.elevation,
                'public_transportation_rating': 'good service',
                'geometry': {
                    'version': self.waypoint6.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [657403, 5691411]}',
                },
                'associations': {'routes': [{'document_id': self.route1.document_id}]},
            },
        }
        resp = self.client.put(
            f'/v2/waypoints/{self.waypoint6.document_id}',
            json=body,
            headers=self._auth_headers(),
        )
        assert resp.status_code == 200, resp.text

        self.session.flush()
        self.session.refresh(self.route1)
        self.session.refresh(self.waypoint6)
        assert self.waypoint6.waypoint_type == 'access'
        assert self.waypoint6.public_transportation_rating == 'good service'
        assert self.route1.public_transportation_rating == 'good service'

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def test_history(self):
        """Document history returns version list with contributor info."""
        doc_id = self.waypoint.document_id
        user_id = global_userids['contributor']
        for lang in ['fr', 'en']:
            resp = self.client.get(f'/v2/document/{doc_id}/history/{lang}')
            assert resp.status_code == 200
            body = resp.json()
            assert body['title'] == self.waypoint.get_locale(lang).title
            versions = body['versions']
            assert len(versions) == 1
            v = versions[0]
            assert v['name'] == 'Contributor'
            assert 'username' not in v
            assert v['user_id'] == user_id
            assert 'written_at' in v
            assert 'version_id' in v

    def _assert_geometry(self, body, field='geom'):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get(field) is not None

        geom = geometry.get(field)
        point = shape(json.loads(geom))
        assert isinstance(point, Point)

    @staticmethod
    def _get_latest_version(lang, versions):
        return max([v for v in versions if v.lang == lang], key=lambda v: v.id)

    # ──────────────────────────────────────────────────────────
    # Association history
    # ──────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        resp = self.client.get(
            f'/v2/associations-history?d={self.waypoint.document_id}'
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body['count'], int)
        assert body['count'] >= 1
        for entry in body['associations']:
            ids = (
                entry['parent_document']['document_id'],
                entry['child_document']['document_id'],
            )
            assert self.waypoint.document_id in ids
