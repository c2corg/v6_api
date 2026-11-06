import pytest

from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale


class TestSitemapXml:
    @pytest.fixture(autouse=True)
    def _setup_test_sitemap_xml(self, client, session):
        self._prefix = '/sitemaps.xml'
        self.ui_url = 'https://www.camptocamp.org'
        self.schema_url = '{http://www.sitemaps.org/schemas/sitemap/0.9}'

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            locales=[WaypointLocale(lang='fr', title='Dent de Crolles')],
        )
        session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            locales=[
                WaypointLocale(lang='en', title='Mont Blanc'),
                WaypointLocale(lang='fr', title='Mont Blanc'),
            ],
        )
        session.add(self.waypoint2)
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
        session.add(self.route)
        session.flush()

    def test_get(self, client):
        response = client.get(self._prefix, status=200)
        sitemaps = response.xml

        base_url = 'https://api.camptocamp.org/sitemaps.xml'

        def waypoint_filter(s):
            return s[0].text == base_url + '/w/0.xml'

        def route_filter(s):
            return s[0].text == base_url + '/r/0.xml'

        assert next(filter(waypoint_filter, sitemaps), None) is not None
        assert next(filter(route_filter, sitemaps), None) is not None

    def test_get_sitemap_invalid_doc_type(self, client):
        response = client.get(
            self._prefix + '/z/0.xml', headers={'Cookie': 'a=b'}, status=422
        )
        # the errors only, as for the JSON routes: not the request headers
        assert response.json == {
            'detail': [
                {
                    'type': 'c2corg',
                    'loc': ['path', 'doc_type'],
                    'msg': 'invalid doc_type',
                    'input': 'z',
                }
            ]
        }

    def test_get_sitemap_invalid_page(self, client):
        # a page that is not a number: not found
        client.get(self._prefix + '/a/-123.xml', status=404)

    def test_get_waypoint_sitemap(self, client):
        response = client.get(self._prefix + '/w/0.xml', status=200)
        urlset = response.xml

        assert len(urlset) == 3
        url = urlset[0]

        assert url[0].tag == f'{self.schema_url}loc'
        assert url[1].tag == f'{self.schema_url}lastmod'
        assert (
            url[0].text == f'{self.ui_url}/waypoints/{self.waypoint1.document_id}'
            '/fr/dent-de-crolles'
        )

    def test_get_waypoint_sitemap_no_pages(self, client):
        client.get(self._prefix + '/w/1.xml', status=404)

    def test_get_route_sitemap(self, client):
        response = client.get(self._prefix + '/r/0.xml', status=200)
        urlset = response.xml

        assert len(urlset) == 1
        url = urlset[0]

        assert url[0].tag == f'{self.schema_url}loc'
        assert url[1].tag == f'{self.schema_url}lastmod'
        assert (
            url[0].text == f'{self.ui_url}/routes/{self.route.document_id}'
            '/fr/mont-blanc-mont-blanc-du-ciel'
        )
