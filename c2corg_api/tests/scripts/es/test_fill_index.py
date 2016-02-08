from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.search.mapping import SearchDocument
from c2corg_api.tests import BaseTestCase
from c2corg_api.scripts.es.fill_index import fill_index


class FillIndexTest(BaseTestCase):

    def test_fill_index(self):
        """Tests that documents are inserted into the ElasticSearch index.
        """
        self.session.add(Waypoint(
            document_id=71171,
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont [b]Granier[/b]'),
                WaypointLocale(
                    lang='en', title='Mont Granier',
                    description='...',
                    summary='The Mont Granier')
            ]))
        self.session.add(Waypoint(
            document_id=71172,
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
            document_id=71173,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            locales=[
                RouteLocale(
                    lang='en', title='Face N',
                    description='...', gear='paraglider',
                    title_prefix='Mont Blanc'
                )
            ]
        ))
        self.session.flush()

        # fill the ElasticSearch index
        fill_index(self.session)

        waypoint1 = SearchDocument.get(id=71171)
        self.assertIsNotNone(waypoint1)
        self.assertEqual(waypoint1.title_en, 'Mont Granier')
        self.assertEqual(waypoint1.title_fr, 'Mont Granier')
        self.assertEqual(waypoint1.summary_fr, 'Le Mont  Granier ')
        self.assertEqual(waypoint1.doc_type, 'w')

        waypoint2 = SearchDocument.get(id=71172)
        self.assertIsNotNone(waypoint2)
        self.assertEqual(waypoint2.title_en, 'Mont Blanc')
        self.assertEqual(waypoint2.title_fr, '')
        self.assertEqual(waypoint2.doc_type, 'w')

        route = SearchDocument.get(id=71173)
        self.assertIsNotNone(route)
        self.assertEqual(route.title_en, 'Mont Blanc : Face N')
        self.assertEqual(route.title_fr, '')
        self.assertEqual(route.doc_type, 'r')
