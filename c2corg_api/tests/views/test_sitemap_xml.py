from c2corg_api.models.route import RouteLocale, Route
from c2corg_api.models.waypoint import WaypointLocale, Waypoint

from c2corg_api.tests.views import BaseTestRest


class TestSitemapXml(BaseTestRest):
    def setUp(self):  # noqa
        super(TestSitemapXml, self).setUp()
        self._prefix = '/sitemaps.xml'
        self.ui_url = 'https://www.camptocamp.org'
        self.schema_url = '{http://www.sitemaps.org/schemas/sitemap/0.9}'

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2000,
            locales=[
                WaypointLocale(
                    lang='fr', title='Dent de Crolles')
            ])
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=4985,
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc'),
                WaypointLocale(
                    lang='fr', title='Mont Blanc')
            ])
        self.session.add(self.waypoint2)
        self.route = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    title_prefix='Mont Blanc'
                )
            ])
        self.session.add(self.route)
        self.session.flush()

    def test_get(self):
        response = self.app.get(self._prefix, status=200)
        sitemaps = response.xml

        base_url = 'https://api.camptocamp.org/sitemaps.xml'

        def waypoint_filter(s):
            return s[0].text == base_url + '/w/0.xml'

        def route_filter(s):
            return s[0].text == base_url + '/r/0.xml'

        self.assertIsNotNone(
            next(filter(waypoint_filter, sitemaps), None)
        )
        self.assertIsNotNone(
            next(filter(route_filter, sitemaps), None)
        )

    def test_get_sitemap_invalid_doc_type(self):
        response = self.app.get(self._prefix + '/z/0.xml', status=400)
        errors = response.json['errors']
        self.assertError(errors, 'doc_type', 'invalid doc_type')

    def test_get_sitemap_invalid_page(self):
        response = self.app.get(self._prefix + '/a/-123.xml', status=400)
        errors = response.json['errors']
        self.assertError(errors, 'i', 'invalid i')

    def test_get_waypoint_sitemap(self):
        response = self.app.get(self._prefix + '/w/0.xml', status=200)
        urlset = response.xml

        self.assertEqual(len(urlset), 3)
        url = urlset[0]

        self.assertEqual(url[0].tag, "{}loc".format(self.schema_url))
        self.assertEqual(url[1].tag, "{}lastmod".format(self.schema_url))
        self.assertEqual(
            url[0].text,
            "{}/waypoints/{}/fr/dent-de-crolles".format(
                self.ui_url,
                self.waypoint1.document_id
            )
        )

    def test_get_waypoint_sitemap_no_pages(self):
        self.app.get(self._prefix + '/w/1.xml', status=404)

    def test_get_route_sitemap(self):
        response = self.app.get(self._prefix + '/r/0.xml', status=200)
        urlset = response.xml

        self.assertEqual(len(urlset), 1)
        url = urlset[0]

        self.assertEqual(url[0].tag, "{}loc".format(self.schema_url))
        self.assertEqual(url[1].tag, "{}lastmod".format(self.schema_url))
        self.assertEqual(
            url[0].text,
            "{}/routes/{}/fr/mont-blanc-mont-blanc-du-ciel".format(
                self.ui_url,
                self.route.document_id
            )
        )
