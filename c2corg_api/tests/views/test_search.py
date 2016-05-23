from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search.search import get_documents
from c2corg_api.tests.search import force_search_index
from c2corg_api.tests.views import BaseTestRest


class TestSearchRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestSearchRest, self).setUp()
        self._prefix = '/search'

        self.waypoint1 = Waypoint(
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
            ])
        self.session.add(self.waypoint1)
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
        self.assertIn('maps', body)
        self.assertIn('areas', body)
        self.assertIn('images', body)
        self.assertIn('outings', body)

        waypoints = body['waypoints']
        self.assertTrue(waypoints['total'] > 0)
        locales = waypoints['documents'][0]['locales']
        self.assertEqual(len(locales), 2)
        self.assertIn('type', waypoints['documents'][0])

        routes = body['routes']
        self.assertEqual(0, routes['total'])

        # tests that user results are not included when not authenticated
        self.assertNotIn('users', body)

    def test_search_lang(self):
        response = self.app.get(self._prefix + '?q=crolles&pl=fr', status=200)
        body = response.json

        self.assertIn('waypoints', body)
        self.assertIn('routes', body)

        waypoints = body['waypoints']
        self.assertTrue(waypoints['total'] > 0)

        locales = waypoints['documents'][0]['locales']
        self.assertEqual(len(locales), 1)

    def test_get_documents_merged_documents(self):
        """Tests that merged documents are ignored.
        """
        waypoint = Waypoint(
            redirects_to=self.waypoint1.document_id,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(waypoint)
        documents = get_documents(
            [waypoint.document_id], Waypoint, DocumentLocale, None)
        self.assertEquals(0, len(documents))

    def test_search_authenticated(self):
        """Tests that user results are included when authenticated.
        """
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(self._prefix + '?q=crolles', headers=headers,
                                status=200)
        body = response.json

        self.assertIn('users', body)
        users = body['users']
        self.assertIn('total', users)

    def test_search_user_unauthenticated(self):
        """Tests that user results are not included when not authenticated.
        """
        response = self.app.get(self._prefix + '?q=alex&t=u', status=200)
        body = response.json

        self.assertNotIn('users', body)

    def test_search_limit_types(self):
        response = self.app.get(self._prefix + '?q=crolles&t=w,r', status=200)
        body = response.json

        self.assertIn('waypoints', body)
        self.assertIn('routes', body)
        self.assertNotIn('maps', body)
        self.assertNotIn('areas', body)
        self.assertNotIn('images', body)
        self.assertNotIn('outings', body)
        self.assertNotIn('users', body)

    def test_search_by_document_id(self):
        response = self.app.get(
            self._prefix + '?q=' + str(self.waypoint1.document_id), status=200)
        body = response.json

        waypoints = body['waypoints']
        self.assertEquals(waypoints['total'], 1)
        self.assertEquals(waypoints['count'], 1)
        self.assertEquals(len(waypoints['documents']), 1)

        routes = body['routes']
        self.assertEquals(routes['total'], 0)
        self.assertEquals(routes['count'], 0)
        self.assertEquals(len(routes['documents']), 0)
