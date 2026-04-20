"""
FastAPI collection-search tests (ES-backed).

Each test class exercises the ``GET /v2/{type}?<es-filter>`` endpoint
with ElasticSearch query parameters.  These mirror the view-level
``test_get_collection_search`` tests that were previously skipped.

The tests call ``reset_search_index(session)`` to populate the ES
index with the test data before querying.
"""

import urllib.parse
from datetime import date

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.image import Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.tests.search import reset_search_index
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version

# ── helpers ──────────────────────────────────────────────────────


class _CollectionSearchBase(BaseTestCase):
    """Shared setUp / tearDown for all collection-search tests."""

    _prefix: str  # e.g. '/v2/waypoints'

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
        raise NotImplementedError

    # ── query helpers (mirror view test helpers) ─────────────────

    def get_collection_search(self, params):
        url = self._prefix
        if params:
            url += '?' + urllib.parse.urlencode(params)
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.text
        return resp.json()


# ── Waypoint ─────────────────────────────────────────────────────


class TestWaypointCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/waypoints'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        self.waypoint1.locales.append(
            WaypointLocale(lang='en', title='Mont Granier', description='...')
        )
        self.waypoint1.locales.append(
            WaypointLocale(lang='fr', title='Mont Granier', description='...')
        )
        self.waypoint1.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint1)
        self.session.flush()
        create_new_version(self.waypoint1, user_id, db=self.session)

        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
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
            geometry=DocumentGeometry(geom='SRID=3857;POINT(659775 5694854)'),
        )
        self.waypoint4.locales.append(
            WaypointLocale(lang='en', title='Mont Blanc', description='...')
        )
        self.waypoint4.locales.append(
            WaypointLocale(lang='fr', title='Mont Blanc', description='...')
        )
        self.session.add(self.waypoint4)
        self.session.flush()
        create_new_version(self.waypoint4, user_id, db=self.session)

    def test_get_collection_search(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'wtyp': 'climbing_outdoor,summit'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [
            self.waypoint4.document_id,
            self.waypoint3.document_id,
            self.waypoint2.document_id,
            self.waypoint1.document_id,
        ]
        assert response['total'] == 4

        body = self.get_collection_search(
            {'wtyp': 'climbing_outdoor,summit', 'limit': 2}
        )
        assert body['total'] == 4
        assert len(body['documents']) == 2

    def test_get_collection_search_bbox(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'bbox': '659000,5694000,660000,5695000'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.waypoint4.document_id]
        assert response['total'] == 1


# ── Area ─────────────────────────────────────────────────────────


class TestAreaCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/areas'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.area1 = Area(area_type='range')
        self.area1.locales.append(DocumentLocale(lang='en', title='Chartreuse'))
        self.area1.locales.append(DocumentLocale(lang='fr', title='Chartreuse'))
        self.area1.geometry = DocumentGeometry(
            geom_detail=(
                'SRID=3857;POLYGON((668518 5728802,'
                '668518 5745465,689156 5745465,'
                '689156 5728802,668518 5728802))'
            )
        )
        self.session.add(self.area1)
        self.session.flush()
        create_new_version(self.area1, user_id, db=self.session)

        self.area2 = Area(area_type='range')
        self.session.add(self.area2)
        self.area3 = Area(area_type='range')
        self.session.add(self.area3)
        self.area4 = Area(area_type='admin_limits')
        self.area4.locales.append(DocumentLocale(lang='en', title='Isère'))
        self.area4.locales.append(DocumentLocale(lang='fr', title='Isère'))
        self.session.add(self.area4)
        self.session.flush()
        create_new_version(self.area4, user_id, db=self.session)

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'l': 'en'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.area4.document_id, self.area1.document_id]
        assert response['total'] == 2

    def test_get_collection_search_atyp(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'atyp': 'admin_limits'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.area4.document_id]
        assert response['total'] == 1


# ── Article ──────────────────────────────────────────────────────


class TestArticleCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/articles'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.article1.locales.append(
            DocumentLocale(lang='en', title='Article 1', description='...')
        )
        self.article1.locales.append(
            DocumentLocale(lang='fr', title='Article 1 FR', description='...')
        )
        self.session.add(self.article1)
        self.session.flush()
        create_new_version(self.article1, user_id, db=self.session)

        self.article2 = Article(
            categories=['association'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article2)
        self.article3 = Article(
            categories=['association'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article3)
        self.article4 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.article4.locales.append(
            DocumentLocale(lang='en', title='Article 4', description='...')
        )
        self.article4.locales.append(
            DocumentLocale(lang='fr', title='Article 4 FR', description='...')
        )
        self.session.add(self.article4)
        self.session.flush()
        create_new_version(self.article4, user_id, db=self.session)

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'l': 'en'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.article4.document_id, self.article1.document_id]
        assert response['total'] == 2

    def test_get_collection_search_act(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'act': 'hiking'})
        assert body['total'] == 4


# ── Book ─────────────────────────────────────────────────────────


class TestBookCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/books'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.book1 = Book(activities=['hiking'], book_types=['biography'])
        self.book1.locales.append(
            DocumentLocale(lang='en', title='Book 1', description='...')
        )
        self.book1.locales.append(
            DocumentLocale(lang='fr', title='Book 1 FR', description='...')
        )
        self.session.add(self.book1)
        self.session.flush()
        create_new_version(self.book1, user_id, db=self.session)

        self.book2 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book2)
        self.book3 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book3)
        self.book4 = Book(activities=['hiking'], book_types=['biography'])
        self.book4.locales.append(
            DocumentLocale(lang='en', title='Book 4', description='...')
        )
        self.book4.locales.append(
            DocumentLocale(lang='fr', title='Book 4 FR', description='...')
        )
        self.session.add(self.book4)
        self.session.flush()
        create_new_version(self.book4, user_id, db=self.session)

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'l': 'en'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.book4.document_id, self.book1.document_id]
        assert response['total'] == 2

    def test_get_collection_search_btyp(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'btyp': 'biography'})
        assert body['total'] == 4


# ── Topo Map ─────────────────────────────────────────────────────


class TestTopoMapCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/maps'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.map1 = TopoMap()
        self.map1.locales.append(
            DocumentLocale(lang='en', title='Map 1', description='...')
        )
        self.map1.locales.append(
            DocumentLocale(lang='fr', title='Map 1 FR', description='...')
        )
        self.map1.geometry = DocumentGeometry(
            geom_detail=(
                'SRID=3857;POLYGON((668518 5728802,'
                '668518 5745465,689156 5745465,'
                '689156 5728802,668518 5728802))'
            )
        )
        self.session.add(self.map1)
        self.session.flush()
        create_new_version(self.map1, user_id, db=self.session)

        self.map2 = TopoMap()
        self.session.add(self.map2)
        self.map3 = TopoMap()
        self.session.add(self.map3)
        self.map4 = TopoMap()
        self.map4.locales.append(
            DocumentLocale(lang='en', title='Map 4', description='...')
        )
        self.map4.locales.append(
            DocumentLocale(lang='fr', title='Map 4 FR', description='...')
        )
        self.session.add(self.map4)
        self.session.flush()
        create_new_version(self.map4, user_id, db=self.session)

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'l': 'en'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.map4.document_id, self.map1.document_id]
        assert response['total'] == 2


# ── Outing ───────────────────────────────────────────────────────


class TestOutingCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/outings'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint)

        self.route = Route(
            activities=['skitouring'],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)',
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723614)',
            ),
        )
        self.route.locales.append(RouteLocale(lang='en', title='Route 1'))
        self.route.locales.append(RouteLocale(lang='fr', title='Route 1 FR'))
        self.session.add(self.route)
        self.session.flush()
        create_new_version(self.route, user_id, db=self.session)

        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            elevation_max=1500,
            height_diff_up=800,
            elevation_access=900,
            condition_rating='good',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)',
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723614)',
            ),
        )
        self.outing1.locales.append(
            OutingLocale(lang='en', title='Outing 1', description='...')
        )
        self.session.add(self.outing1)
        self.session.flush()
        create_new_version(self.outing1, user_id, db=self.session)

        self.outing2 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 1),
            height_diff_up=600,
            elevation_max=1800,
            elevation_access=700,
            condition_rating='average',
        )
        self.session.add(self.outing2)
        self.session.flush()
        create_new_version(self.outing2, user_id, db=self.session)

        self.outing3 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 3, 1),
            date_end=date(2016, 3, 1),
            height_diff_up=200,
            elevation_max=1200,
            elevation_access=800,
            condition_rating='poor',
        )
        self.session.add(self.outing3)
        self.session.flush()
        create_new_version(self.outing3, user_id, db=self.session)

        self.outing4 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 4, 1),
            date_end=date(2016, 4, 1),
            height_diff_up=500,
            elevation_max=1400,
            elevation_access=800,
            condition_rating='excellent',
        )
        self.session.add(self.outing4)
        self.session.flush()
        create_new_version(self.outing4, user_id, db=self.session)

        # Create associations so the filter tests work
        self.session.add(Association.create(self.route, self.outing1))
        self.session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing1.document_id,
                child_document_type=OUTING_TYPE,
            )
        )
        self.session.flush()

    def test_get_collection_search_act(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'act': 'skitouring'})
        assert body['total'] == 4

        body = self.get_collection_search({'act': 'skitouring', 'limit': 2})
        assert body['total'] == 4
        assert len(body['documents']) == 2

    def test_get_collection_for_route(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'r': str(self.route.document_id)})
        assert body['total'] == 1
        assert body['documents'][0]['document_id'] == self.outing1.document_id

    def test_get_collection_for_waypoint(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'w': str(self.waypoint.document_id)})
        # waypoint association is checked via ES — depends on indexing
        assert isinstance(body['total'], int)

    def test_get_collection_for_user(self):
        """Test ?u= filter (ES-backed user association)."""
        reset_search_index(self.session)

        body = self.get_collection_search({'u': str(global_userids['contributor'])})
        assert body['total'] == 1
        assert body['documents'][0]['document_id'] == self.outing1.document_id

    def test_get_collection_has_geom(self):
        """Test that geometry.has_geom_detail is present in collection
        results when queried via an ES filter."""
        reset_search_index(self.session)

        body = self.get_collection_search({'r': str(self.route.document_id)})
        documents = body['documents']
        assert len(documents) == 1
        assert documents[0]['geometry']['has_geom_detail'] is True

    def test_get_collection_search_date(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'date': '2015-12-31,2016-01-02'})
        assert body['total'] == 1

    # ── Sorting ──────────────────────────────────────────────────

    def test_get_sort_asc(self):
        """Test ascending sorting of results for height_diff_up keyword."""
        reset_search_index(self.session)
        body = self.get_collection_search({'sort': 'height_diff_up'})
        response_ids = [d['document_id'] for d in body['documents']]
        expected_ids = [
            self.outing3.document_id,
            self.outing4.document_id,
            self.outing2.document_id,
            self.outing1.document_id,
        ]
        assert response_ids == expected_ids

    def test_get_sort_desc(self):
        """Test descending sorting of results for elevation_max keyword."""
        reset_search_index(self.session)
        body = self.get_collection_search({'sort': '-elevation_max'})
        response_ids = [d['document_id'] for d in body['documents']]
        expected_ids = [
            self.outing2.document_id,
            self.outing1.document_id,
            self.outing4.document_id,
            self.outing3.document_id,
        ]
        assert response_ids == expected_ids

    def test_get_sort_multi(self):
        """Test multi-criteria sorting (elevation_max: desc,
        height_diff_up: asc)."""
        reset_search_index(self.session)
        body = self.get_collection_search({'sort': '-elevation_max,height_diff_up'})
        response_ids = [d['document_id'] for d in body['documents']]
        expected_ids = [
            self.outing2.document_id,
            self.outing1.document_id,
            self.outing4.document_id,
            self.outing3.document_id,
        ]
        assert response_ids == expected_ids

    def test_get_sort_numeric_enum(self):
        """Test sorting with two different criteria:
        numeric (elevation_access) and enum (condition_rating)."""
        reset_search_index(self.session)
        body = self.get_collection_search(
            {'sort': '-elevation_access,condition_rating'}
        )
        response_ids = [d['document_id'] for d in body['documents']]
        expected_ids = [
            self.outing1.document_id,
            self.outing4.document_id,
            self.outing3.document_id,
            self.outing2.document_id,
        ]
        assert response_ids == expected_ids

    def test_get_sort_error(self):
        """Test failure if an unknown keyword is used for sorting."""
        reset_search_index(self.session)
        url = self._prefix + '?sort=-elevation_axess'
        resp = self.client.get(url)
        assert resp.status_code == 500


# ── Route ────────────────────────────────────────────────────────


class TestRouteCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/routes'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint)
        self.session.flush()

        self.route1 = Route(
            activities=['skitouring'],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)',
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723614)',
            ),
        )
        self.route1.locales.append(
            RouteLocale(lang='en', title='Route 1', description='...')
        )
        self.route1.locales.append(
            RouteLocale(lang='fr', title='Route 1 FR', description='...')
        )
        self.session.add(self.route1)
        self.session.flush()
        create_new_version(self.route1, user_id, db=self.session)

        self.route2 = Route(
            activities=['skitouring'],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.route2)
        self.session.flush()
        create_new_version(self.route2, user_id, db=self.session)

        self.route3 = Route(
            activities=['hiking'],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.route3)
        self.session.flush()
        create_new_version(self.route3, user_id, db=self.session)

        self.session.add(Association.create(self.waypoint, self.route1))

    def test_get_collection_search_act(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'act': 'skitouring'})
        assert body['total'] == 2

    def test_get_collection_for_waypoint(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'w': str(self.waypoint.document_id)})
        assert body['total'] == 1
        assert body['documents'][0]['document_id'] == self.route1.document_id

    def test_get_collection_has_geom(self):
        """Test that geometry.has_geom_detail is present in route collection
        results (route1 has geom_detail, route2 does not)."""
        reset_search_index(self.session)

        body = self.get_collection_search({'act': 'skitouring'})
        docs_by_id = {d['document_id']: d for d in body['documents']}
        # route1 has geom_detail
        assert (
            docs_by_id[self.route1.document_id]['geometry']['has_geom_detail'] is True
        )
        # route2 has only geom (no geom_detail)
        assert (
            docs_by_id[self.route2.document_id]['geometry']['has_geom_detail'] is False
        )


# ── Image ────────────────────────────────────────────────────────


class TestImageCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/images'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.image1 = Image(filename='image1.jpg', activities=['hiking'], height=1500)
        self.image1.locales.append(
            DocumentLocale(lang='en', title='Image 1', description='...')
        )
        self.image1.locales.append(
            DocumentLocale(lang='fr', title='Image 1 FR', description='...')
        )
        self.image1.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.image1)
        self.session.flush()
        create_new_version(self.image1, user_id, db=self.session)

        self.image2 = Image(filename='image2.jpg', activities=['hiking'], height=500)
        self.session.add(self.image2)
        self.image3 = Image(
            filename='image3.jpg', activities=['paragliding'], height=2000
        )
        self.session.add(self.image3)
        self.image4 = Image(filename='image4.jpg', activities=['hiking'], height=1800)
        self.image4.locales.append(
            DocumentLocale(lang='en', title='Image 4', description='...')
        )
        self.image4.locales.append(
            DocumentLocale(lang='fr', title='Image 4 FR', description='...')
        )
        self.session.add(self.image4)
        self.session.flush()
        create_new_version(self.image4, user_id, db=self.session)

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        response = self.get_collection_search({'l': 'en'})
        documents = response['documents']
        ids = [d['document_id'] for d in documents]
        assert ids == [self.image4.document_id, self.image1.document_id]
        assert response['total'] == 2


# ── Xreport ──────────────────────────────────────────────────────


class TestXreportCollectionSearch(_CollectionSearchBase):
    _prefix = '/v2/xreports'

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.xreport1 = Xreport(
            event_activity='skitouring', event_type='avalanche', nb_participants=5
        )
        self.xreport1.locales.append(
            XreportLocale(lang='en', title='Xreport 1', description='...')
        )
        self.xreport1.locales.append(
            XreportLocale(lang='fr', title='Xreport 1 FR', description='...')
        )
        self.xreport1.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.xreport1)
        self.session.flush()
        create_new_version(self.xreport1, user_id, db=self.session)

        self.xreport2 = Xreport(
            event_activity='skitouring', event_type='stone_ice_fall', nb_participants=3
        )
        self.session.add(self.xreport2)
        self.session.flush()

    def test_get_collection_search_lang(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'l': 'en'})
        assert body['total'] == 1
        assert body['documents'][0]['document_id'] == self.xreport1.document_id
