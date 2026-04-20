"""
Tests for the FastAPI sitemap XML router (``/v2/sitemaps.xml``).

Mirrors ``c2corg_api/tests/views/test_sitemap_xml.py``.
"""

from xml.etree import ElementTree

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestSitemapXmlRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self.ui_url = 'https://www.camptocamp.org'
        self.schema_url = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
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
        r = self.client.get('/v2/sitemaps.xml')
        assert r.status_code == 200
        sitemaps = ElementTree.fromstring(r.content)

        base_url = 'https://api.camptocamp.org/sitemaps.xml'

        def waypoint_filter(s):
            return s[0].text == base_url + '/w/0.xml'

        def route_filter(s):
            return s[0].text == base_url + '/r/0.xml'

        assert next(filter(waypoint_filter, sitemaps), None) is not None
        assert next(filter(route_filter, sitemaps), None) is not None

    def test_get_sitemap_invalid_doc_type(self):
        r = self.client.get('/v2/sitemaps.xml/z/0.xml')
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'doc_type' and e.get('description') == 'invalid doc_type'
            for e in errors
        )

    def test_get_sitemap_invalid_page(self):
        r = self.client.get('/v2/sitemaps.xml/a/-123.xml')
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'i' and e.get('description') == 'invalid i' for e in errors
        )

    def test_get_waypoint_sitemap(self):
        r = self.client.get('/v2/sitemaps.xml/w/0.xml')
        assert r.status_code == 200
        urlset = ElementTree.fromstring(r.content)

        assert len(urlset) == 3
        url = urlset[0]

        assert url[0].tag == '{}loc'.format(self.schema_url)
        assert url[1].tag == '{}lastmod'.format(self.schema_url)
        assert url[0].text == '{}/waypoints/{}/fr/dent-de-crolles'.format(
            self.ui_url, self.waypoint1.document_id
        )

    def test_get_waypoint_sitemap_no_pages(self):
        r = self.client.get('/v2/sitemaps.xml/w/1.xml')
        assert r.status_code == 404

    def test_get_route_sitemap(self):
        r = self.client.get('/v2/sitemaps.xml/r/0.xml')
        assert r.status_code == 200
        urlset = ElementTree.fromstring(r.content)

        assert len(urlset) == 1
        url = urlset[0]

        assert url[0].tag == '{}loc'.format(self.schema_url)
        assert url[1].tag == '{}lastmod'.format(self.schema_url)
        assert url[0].text == '{}/routes/{}/fr/mont-blanc-mont-blanc-du-ciel'.format(
            self.ui_url, self.route.document_id
        )
