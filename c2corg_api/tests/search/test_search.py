from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import BaseTestCase
from c2corg_api.search import search


class SearchTest(BaseTestCase):

    def test_get_documents(self):
        """Tests that documents keep the order of the list of ids.
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
                    summary='Le Mont Granier')
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

        docs = search.get_documents([71171, 71172], Waypoint)
        self.assertEqual(71171, docs[0].document_id)
        self.assertEqual(71172, docs[1].document_id)

        docs = search.get_documents([71172, 71171], Waypoint)
        self.assertEqual(71172, docs[0].document_id)
        self.assertEqual(71171, docs[1].document_id)
