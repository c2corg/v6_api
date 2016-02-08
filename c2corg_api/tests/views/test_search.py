from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.tests.search import force_search_index
from c2corg_api.tests.views import BaseTestRest


class TestSearchRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestSearchRest, self).setUp()
        self._prefix = '/search'

        self.session.add(Waypoint(
            document_id=534681,
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles'),
                WaypointLocale(
                    lang='en', title='Dent de Crolles',
                    description='...',
                    summary='The Dent de Crolles')
            ]))
        self.session.add(Waypoint(
            document_id=534682,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ]))
        self.session.add(Route(
            document_id=534683,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ]))
        self.session.flush()
        fill_index(self.session)
        # make sure the search index is built
        force_search_index()

    def test_search(self):
        response = self.app.get(self._prefix + '?q=crolles', status=200)
        body = response.json

        self.assertIn('waypoints', body)
        self.assertIn('routes', body)

        waypoints = body['waypoints']
        self.assertTrue(waypoints['total'] > 0)
        locales = waypoints['documents'][0]['locales']
        self.assertEqual(len(locales), 2)

        routes = body['routes']
        self.assertEqual(0, routes['total'])

    def test_search_lang(self):
        response = self.app.get(self._prefix + '?q=crolles&pl=fr', status=200)
        body = response.json

        self.assertIn('waypoints', body)
        self.assertIn('routes', body)

        waypoints = body['waypoints']
        self.assertTrue(waypoints['total'] > 0)

        locales = waypoints['documents'][0]['locales']
        self.assertEqual(len(locales), 1)
