from c2corg_api.models.document import DocumentGeometry
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
                    culture='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont Granier'),
                WaypointLocale(
                    culture='en', title='Mont Granier',
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
                    culture='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ]))
        self.session.flush()

        # fill the ElasticSearch index
        fill_index(self.session)

        waypoint1 = SearchDocument.get(id=71171)
        self.assertIsNotNone(waypoint1)
        self.assertEqual(waypoint1.title_en, 'Mont Granier')
        self.assertEqual(waypoint1.title_fr, 'Mont Granier')

        waypoint2 = SearchDocument.get(id=71172)
        self.assertIsNotNone(waypoint2)
        self.assertEqual(waypoint2.title_en, 'Mont Blanc')
        self.assertEqual(waypoint2.title_fr, '')
