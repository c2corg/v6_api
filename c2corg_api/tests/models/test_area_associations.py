from c2corg_api.models.area import Area
from c2corg_api.models.area_association import update_area, AreaAssociation, \
    update_document
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint

from c2corg_api.tests import BaseTestCase


class TestAreaAssociation(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

        self.area = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
        )
        # wp inside the area
        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)')
        )
        # wp outside the area
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(693666.031687976 5741108.7574713)')
        )
        # wp without geometry
        self.waypoint3 = Waypoint(
            waypoint_type='summit'
        )
        # wp with empty geometry
        self.waypoint4 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry()
        )
        self.session.add_all([
            self.area, self.waypoint1, self.waypoint2, self.waypoint3,
            self.waypoint4])
        self.session.flush()

    def test_update_area(self):
        update_area(self.area)

        added_links = self.session.query(AreaAssociation). \
            filter(AreaAssociation.area_id == self.area.document_id).all()
        self.assertEqual(len(added_links), 1)
        self.assertEqual(
            added_links[0].document_id, self.waypoint1.document_id)

    def test_update_area_reset_first(self):
        # add an association with wp2, which should be removed after the update
        self.session.add(AreaAssociation(
            document_id=self.waypoint2.document_id,
            area_id=self.area.document_id))
        self.session.flush()

        update_area(self.area, reset=True)

        updated_links = self.session.query(AreaAssociation). \
            filter(AreaAssociation.area_id == self.area.document_id).all()
        self.assertEqual(len(updated_links), 1)
        self.assertEqual(
            updated_links[0].document_id, self.waypoint1.document_id)

    def test_update_document(self):
        # waypoint inside the area
        update_document(self.waypoint1)

        added_links = self._get_links_for_document(self.waypoint1)
        self.assertEqual(len(added_links), 1)
        self.assertEqual(
            added_links[0].area_id, self.area.document_id)

        # wp outside the area
        update_document(self.waypoint2)

        added_links = self._get_links_for_document(self.waypoint2)
        self.assertEqual(len(added_links), 0)

        # wp without geometry
        update_document(self.waypoint3)

        added_links = self._get_links_for_document(self.waypoint3)
        self.assertEqual(len(added_links), 0)

        # wp with empty geometry
        update_document(self.waypoint4)

        added_links = self._get_links_for_document(self.waypoint4)
        self.assertEqual(len(added_links), 0)

    def test_update_document_reset_first(self):
        # add an association with wp2, which should be removed after the update
        self.session.add(AreaAssociation(
            document_id=self.waypoint2.document_id,
            area_id=self.area.document_id))
        self.session.flush()

        update_document(self.waypoint2, reset=True)

        updated_links = self._get_links_for_document(self.waypoint2)
        self.assertEqual(len(updated_links), 0)

    def _get_links_for_document(self, doc):
        return self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.document_id == doc.document_id). \
            all()
