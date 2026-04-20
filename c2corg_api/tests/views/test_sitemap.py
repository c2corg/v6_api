from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.views import BaseTestRest


class TestSitemapRest(BaseTestRest):
    def setUp(self):  # noqa
        super(TestSitemapRest, self).setUp()
        self._prefix = '/sitemaps'

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
        response = self.app.get(self._prefix, status=200)
        body = response.json

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
        response = self.app.get(self._prefix + '/z/0', status=400)
        errors = response.json['errors']
        self.assertError(errors, 'doc_type', 'invalid doc_type')

    def test_get_sitemap_invalid_page(self):
        response = self.app.get(self._prefix + '/a/-123', status=400)
        errors = response.json['errors']
        self.assertError(errors, 'i', 'invalid i')

    def test_get_waypoint_sitemap(self):
        response = self.app.get(self._prefix + '/w/0', status=200)
        body = response.json

        pages = body['pages']
        assert len(pages) == 3
        page1 = pages[0]
        assert self.waypoint1.document_id == page1['document_id']
        assert 'title' in page1
        assert 'lang' in page1
        assert 'lastmod' in page1

    def test_get_waypoint_sitemap_no_pages(self):
        self.app.get(self._prefix + '/w/1', status=404)

    def test_get_route_sitemap(self):
        response = self.app.get(self._prefix + '/r/0', status=200)
        body = response.json

        pages = body['pages']
        assert len(pages) == 1
        page1 = pages[0]
        assert self.route.document_id == page1['document_id']
        assert 'title' in page1
        assert 'title_prefix' in page1
        assert 'lang' in page1
        assert 'lastmod' in page1
