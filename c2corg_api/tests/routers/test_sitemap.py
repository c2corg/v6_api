"""
Tests for the FastAPI sitemap router (JSON) (``/v2/sitemaps``).

Mirrors ``c2corg_api/tests/views/test_sitemap.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestSitemapRouter(BaseTestCase):
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
        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            locales=[WaypointLocale(lang='fr', title='Dent de Crolles')],
        )
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            locales=[
                WaypointLocale(lang='en', title='Mont Blanc'),
                WaypointLocale(lang='fr', title='Mont Blanc'),
            ],
        )
        self.session.add(self.waypoint2)
        self.route = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel', title_prefix='Mont Blanc'
                )
            ],
        )
        self.session.add(self.route)
        self.session.flush()

    def test_get(self):
        r = self.client.get('/v2/sitemaps')
        assert r.status_code == 200
        body = r.json()

        sitemaps = body['sitemaps']
        assert (
            next(filter(lambda s: s['url'] == '/sitemaps/w/0', sitemaps), None)
            is not None
        )
        assert (
            next(filter(lambda s: s['url'] == '/sitemaps/r/0', sitemaps), None)
            is not None
        )

    def test_get_sitemap_invalid_doc_type(self):
        r = self.client.get('/v2/sitemaps/z/0')
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'doc_type' and e.get('description') == 'invalid doc_type'
            for e in errors
        )

    def test_get_sitemap_invalid_page(self):
        r = self.client.get('/v2/sitemaps/a/-123')
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'i' and e.get('description') == 'invalid i' for e in errors
        )

    def test_get_waypoint_sitemap(self):
        r = self.client.get('/v2/sitemaps/w/0')
        assert r.status_code == 200
        body = r.json()

        pages = body['pages']
        assert len(pages) == 3
        page1 = pages[0]
        assert self.waypoint1.document_id == page1['document_id']
        assert 'title' in page1
        assert 'lang' in page1
        assert 'lastmod' in page1

    def test_get_waypoint_sitemap_no_pages(self):
        r = self.client.get('/v2/sitemaps/w/1')
        assert r.status_code == 404

    def test_get_route_sitemap(self):
        r = self.client.get('/v2/sitemaps/r/0')
        assert r.status_code == 200
        body = r.json()

        pages = body['pages']
        assert len(pages) == 1
        page1 = pages[0]
        assert self.route.document_id == page1['document_id']
        assert 'title' in page1
        assert 'title_prefix' in page1
        assert 'lang' in page1
        assert 'lastmod' in page1
