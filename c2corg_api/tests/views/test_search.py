from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search import elasticsearch_config
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
                    culture='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont Granier')
            ]))
        self.session.add(Waypoint(
            document_id=534682,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    culture='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ]))
        self.session.add(Route(
            document_id=534683,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            locales=[
                RouteLocale(
                    culture='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ]))
        self.session.flush()
        fill_index(self.session)
        # make sure the search index is built
        elasticsearch_config['client'].indices.refresh(
            elasticsearch_config['index'])

    def test_search(self):
        response = self.app.get(self._prefix + '?q=granier', status=200)
        body = response.json

        self.assertIn('waypoints', body)
        self.assertIn('routes', body)

        waypoints = body['waypoints']
        self.assertTrue(waypoints['total'] > 0)

        routes = body['routes']
        self.assertEqual(0, routes['total'])
