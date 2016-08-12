from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import update_map, \
    TopoMapAssociation, update_maps_for_document, get_maps
from c2corg_api.models.waypoint import Waypoint

from c2corg_api.tests import BaseTestCase


class TestTopoMapAssociation(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

        self.map1 = TopoMap(
            code='3232ET',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
        )
        self.session.add(self.map1)
        self.session.flush()
        self.map2 = TopoMap(
            code='3233ET',
            redirects_to=self.map1.document_id,
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
        )

        # wp inside the area of the map
        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)')
        )
        # wp outside the area of the map
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
            self.map2, self.waypoint1, self.waypoint2, self.waypoint3,
            self.waypoint4])
        self.session.flush()

        # wp inside the area of the map, but with `redirects_to`
        # (should be ignored)
        self.waypoint5 = Waypoint(
            waypoint_type='summit',
            redirects_to=self.waypoint1.document_id,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)')
        )
        self.session.add(self.waypoint5)

    def test_update_map(self):
        update_map(self.map1)

        added_links = self.session.query(TopoMapAssociation). \
            filter(TopoMapAssociation.topo_map_id == self.map1.document_id). \
            all()
        self.assertEqual(len(added_links), 1)
        self.assertEqual(
            added_links[0].document_id, self.waypoint1.document_id)

    def test_update_map_reset_first(self):
        # add an association with wp2, which should be removed after the update
        self.session.add(TopoMapAssociation(
            document_id=self.waypoint2.document_id,
            topo_map_id=self.map1.document_id))
        self.session.flush()

        update_map(self.map1, reset=True)

        updated_links = self.session.query(TopoMapAssociation). \
            filter(TopoMapAssociation.topo_map_id == self.map1.document_id). \
            all()
        self.assertEqual(len(updated_links), 1)
        self.assertEqual(
            updated_links[0].document_id, self.waypoint1.document_id)

    def test_update_map_reset_first_forwarded(self):
        """Tests that maps with `redirects_to` are ignored.
        """
        # add an association with wp2, which should be removed after the update
        self.session.add(TopoMapAssociation(
            document_id=self.waypoint2.document_id,
            topo_map_id=self.map2.document_id))
        self.session.flush()

        update_map(self.map2, reset=True)

        updated_links = self.session.query(TopoMapAssociation). \
            filter(TopoMapAssociation.topo_map_id == self.map2.document_id). \
            all()
        self.assertEqual(len(updated_links), 0)

    def test_update_document(self):
        # waypoint inside the area
        update_maps_for_document(self.waypoint1)

        added_links = self._get_links_for_document(self.waypoint1)
        self.assertEqual(len(added_links), 1)
        self.assertEqual(
            added_links[0].topo_map_id, self.map1.document_id)

        # wp outside the area of the map
        update_maps_for_document(self.waypoint2)

        added_links = self._get_links_for_document(self.waypoint2)
        self.assertEqual(len(added_links), 0)

        # wp without geometry
        update_maps_for_document(self.waypoint3)

        added_links = self._get_links_for_document(self.waypoint3)
        self.assertEqual(len(added_links), 0)

        # wp with empty geometry
        update_maps_for_document(self.waypoint4)

        added_links = self._get_links_for_document(self.waypoint4)
        self.assertEqual(len(added_links), 0)

    def test_update_document_forwarded(self):
        # waypoint inside the area of the map but forwarded (should be ignored)
        update_maps_for_document(self.waypoint5)

        added_links = self._get_links_for_document(self.waypoint1)
        self.assertEqual(len(added_links), 0)

    def test_update_document_reset_first(self):
        # add an association with wp2, which should be removed after the update
        self.session.add(TopoMapAssociation(
            document_id=self.waypoint2.document_id,
            topo_map_id=self.map1.document_id))
        self.session.flush()

        update_maps_for_document(self.waypoint2, reset=True)

        updated_links = self._get_links_for_document(self.waypoint2)
        self.assertEqual(len(updated_links), 0)

    def test_get_maps(self):
        update_map(self.map1)
        maps = get_maps(self.waypoint1, 'en')

        self.assertEqual(len(maps), 1)
        self.assertEqual(
            maps[0].document_id, self.map1.document_id)

    def test_get_maps_forwarded(self):
        """Tests that forwarded maps are not included.
        """
        # add an association with wp1
        self.session.add(TopoMapAssociation(
            document_id=self.waypoint1.document_id,
            topo_map_id=self.map2.document_id))
        self.session.flush()
        areas = get_maps(self.waypoint1, 'en')

        self.assertEqual(len(areas), 0)

    def _get_links_for_document(self, doc):
        return self.session.query(TopoMapAssociation). \
            filter(
            TopoMapAssociation.document_id == doc.document_id). \
            all()
