"""
Tests for the FastAPI search router (``/v2/search``).

Mirrors ``c2corg_api/tests/views/test_search.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.tests.search import force_search_index


class TestSearchRouter(BaseTestCase):
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

    def _add_test_data(self):
        self.article1 = Article(
            categories=['site_info'],
            activities=['hiking'],
            article_type='collab',
            locales=[
                DocumentLocale(
                    lang='en',
                    title="Lac d'Annecy",
                    description='...',
                    summary="Lac d'Annecy",
                ),
                DocumentLocale(
                    lang='en',
                    title="Lac d'Annecy",
                    description='...',
                    summary="Lac d'Annecy",
                ),
            ],
        )
        self.session.add(self.article1)
        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles',
                ),
                WaypointLocale(
                    lang='en',
                    title='Dent de Crolles',
                    description='...',
                    summary='The Dent de Crolles',
                ),
            ],
        )
        self.session.add(self.waypoint1)
        self.session.add(
            Waypoint(
                waypoint_type='summit',
                elevation=4985,
                geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
                locales=[
                    WaypointLocale(
                        lang='en',
                        title='Mont Blanc',
                        description='...',
                        summary='The heighest point in Europe',
                    )
                ],
            )
        )
        self.session.add(
            Route(
                activities=['skitouring'],
                elevation_max=1500,
                elevation_min=700,
                locales=[
                    RouteLocale(
                        lang='fr',
                        title='Mont Blanc du ciel',
                        description='...',
                        summary='Ski',
                    )
                ],
            )
        )
        self.book1 = Book(
            activities=['hiking'],
            book_types=['biography'],
            locales=[
                DocumentLocale(
                    lang='en',
                    title="Lac d'Annecy",
                    description='...',
                    summary="Lac d'Annecy",
                ),
                DocumentLocale(
                    lang='en',
                    title="Lac d'Annecy",
                    description='...',
                    summary="Lac d'Annecy",
                ),
            ],
        )
        self.session.add(self.book1)
        self.session.flush()
        fill_index(self.session)
        # make sure the search index is built
        force_search_index()

    def test_search(self):
        r = self.client.get('/v2/search?q=crolles')
        assert r.status_code == 200
        body = r.json()

        assert 'waypoints' in body
        assert 'routes' in body
        assert 'maps' in body
        assert 'areas' in body
        assert 'articles' in body
        assert 'images' in body
        assert 'outings' in body
        assert 'books' in body

        waypoints = body['waypoints']
        assert waypoints['total'] > 0
        locales = waypoints['documents'][0]['locales']
        assert len(locales) == 2
        assert 'type' in waypoints['documents'][0]

        routes = body['routes']
        assert 0 == routes['total']

        # tests that user results are not included when not authenticated
        assert 'users' not in body

    def test_search_by_article_title(self):
        r = self.client.get('/v2/search?q=' + str(self.article1.locales[0].title))
        assert r.status_code == 200
        body = r.json()
        articles = body['articles']

        assert len(articles) == 2
        assert articles['total'] != 0

    def test_search_by_book_title(self):
        r = self.client.get('/v2/search?q=' + str(self.book1.locales[0].title))
        assert r.status_code == 200
        body = r.json()
        books = body['books']

        assert len(books) == 2
        assert books['total'] != 0

    def test_search_lang(self):
        r = self.client.get('/v2/search?q=crolles&pl=fr')
        assert r.status_code == 200
        body = r.json()

        assert 'waypoints' in body
        assert 'routes' in body

        waypoints = body['waypoints']
        assert waypoints['total'] > 0

        locales = waypoints['documents'][0]['locales']
        assert len(locales) == 1

    def test_search_authenticated(self):
        """Tests that user results are included when authenticated."""
        headers = self._auth_headers(username='contributor')
        r = self.client.get('/v2/search?q=crolles', headers=headers)
        assert r.status_code == 200
        body = r.json()

        assert 'users' in body
        users = body['users']
        assert 'total' in users

    def test_search_user_unauthenticated(self):
        """Tests that user results are not included when not authenticated."""
        r = self.client.get('/v2/search?q=alex&t=u')
        assert r.status_code == 200
        body = r.json()

        assert 'users' not in body

    def test_search_limit_types(self):
        r = self.client.get('/v2/search?q=crolles&t=w,r,c,b')
        assert r.status_code == 200
        body = r.json()

        assert 'waypoints' in body
        assert 'routes' in body
        assert 'articles' in body
        assert 'books' in body
        assert 'maps' not in body
        assert 'areas' not in body
        assert 'images' not in body
        assert 'outings' not in body
        assert 'users' not in body

    def test_search_by_document_id(self):
        """Searching by a numeric document_id returns that document."""
        r = self.client.get(f'/v2/search?q={self.waypoint1.document_id}')
        assert r.status_code == 200
        body = r.json()

        waypoints = body['waypoints']
        assert len(waypoints['documents']) == 1
        assert waypoints['total'] == 1

        routes = body['routes']
        assert len(routes['documents']) == 0
        assert routes['total'] == 0
