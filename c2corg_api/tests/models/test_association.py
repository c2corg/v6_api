from c2corg_api.models.association import _get_current_associations, \
    Association, _diff_associations, synchronize_associations
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE
from c2corg_api.tests import BaseTestCase


class TestAssociation(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

        self.waypoint1 = Waypoint(waypoint_type='summit')
        self.waypoint2 = Waypoint(waypoint_type='summit')
        self.route1 = Route(activities=['hiking'])
        self.route2 = Route(activities=['hiking'])
        self.user_profile1 = UserProfile()
        self.user_profile2 = UserProfile()
        self.session.add_all([
            self.waypoint1, self.waypoint2, self.route1, self.route2,
            self.user_profile1, self.user_profile2])
        self.session.flush()

    def _add_test_data_routes(self):
        self.session.add_all([
            Association.create(
                parent_document=self.route1, child_document=self.route2),
            Association.create(
                parent_document=self.waypoint1, child_document=self.route1),
            Association.create(
                parent_document=self.waypoint2, child_document=self.route1),
        ])
        self.session.flush()

    def test_get_current_associations_routes(self):
        self._add_test_data_routes()

        new_associations = {
            'routes': [
                {'document_id': 1, 'is_parent': True}
            ],
            'waypoints': [
                {'document_id': 2, 'is_parent': True}
            ]
        }

        current_associations = _get_current_associations(
            self.route1, new_associations)

        expected_current_associations = {
            'routes': [
                {'document_id': self.route2.document_id, 'is_parent': False}
            ],
            'waypoints': [
                {
                    'document_id': self.waypoint1.document_id,
                    'is_parent': True
                },
                {
                    'document_id': self.waypoint2.document_id,
                    'is_parent': True
                }
            ]
        }
        self.assertEqual(current_associations, expected_current_associations)

    def test_get_current_associations_routes_partial(self):
        """ Check that only those types are loaded that are also given in the
        new associations (e.g. waypoints are not loaded in this case because
        the type is not given as input).
        """
        self._add_test_data_routes()

        new_associations = {
            'routes': [
                {'document_id': 1, 'is_parent': True}
            ]
        }

        current_associations = _get_current_associations(
            self.route1, new_associations)

        expected_current_associations = {
            'routes': [
                {'document_id': self.route2.document_id, 'is_parent': False}
            ]
        }
        self.assertEqual(current_associations, expected_current_associations)

    def test_get_current_associations_waypoints(self):
        self.waypoint3 = Waypoint(waypoint_type='summit')
        self.session.add(self.waypoint3)
        self.session.flush()
        self.session.add_all([
            Association.create(
                parent_document=self.waypoint1, child_document=self.waypoint2),
            Association.create(
                parent_document=self.waypoint3, child_document=self.waypoint1),
            Association.create(
                parent_document=self.waypoint1, child_document=self.route1),
            Association.create(
                parent_document=self.waypoint1, child_document=self.route2),
        ])
        self.session.flush()

        new_associations = {
            # routes are ignored
            'routes': [
                {'document_id': 1, 'is_parent': True},
                {'document_id': 2, 'is_parent': True}
            ],
            'waypoints': [
                {'document_id': 3, 'is_parent': True}
            ],
            'waypoint_children': [
                {'document_id': 4, 'is_parent': False}
            ]
        }

        current_associations = _get_current_associations(
            self.waypoint1, new_associations)

        expected_current_associations = {
            'waypoints': [
                {
                    'document_id': self.waypoint3.document_id,
                    'is_parent': True
                }
            ],
            'waypoint_children': [
                {
                    'document_id': self.waypoint2.document_id,
                    'is_parent': False
                }
            ]
        }
        self.assertEqual(current_associations, expected_current_associations)

    def test_get_current_associations_waypoints_partial(self):
        self.session.add(Association.create(
            parent_document=self.waypoint1, child_document=self.waypoint2)
        )
        self.session.flush()

        new_associations = {}
        current_associations = _get_current_associations(
            self.waypoint1, new_associations)

        expected_current_associations = {}
        self.assertEqual(current_associations, expected_current_associations)

    def test_diff_associations(self):
        new_associations = {
            'routes': [
                {'document_id': 1, 'is_parent': True},
                {'document_id': 2, 'is_parent': True}
            ],
            'waypoints': [
                {'document_id': 3, 'is_parent': False}
            ]
        }
        current_associations = {
            'routes': [
                {'document_id': 1, 'is_parent': True},
                {'document_id': 4, 'is_parent': True}
            ],
            'waypoints': []
        }

        to_add, to_remove = _diff_associations(
            new_associations, current_associations)

        expected_to_add = [
            {'document_id': 2, 'is_parent': True, 'doc_type': ROUTE_TYPE},
            {'document_id': 3, 'is_parent': False, 'doc_type': WAYPOINT_TYPE}
        ]

        expected_to_remove = [
            {'document_id': 4, 'is_parent': True, 'doc_type': ROUTE_TYPE}
        ]

        self.assertEqual(
            _get_document_ids(to_add),
            _get_document_ids(expected_to_add))
        self.assertEqual(
            _get_document_ids(to_remove),
            _get_document_ids(expected_to_remove))

    def test_synchronize_associations(self):
        self.route3 = Route(activities=['hiking'])
        self.route4 = Route(activities=['hiking'])
        self.session.add_all([self.route3, self.route4])
        self.session.flush()
        self.session.add_all([
            Association.create(
                parent_document=self.route1, child_document=self.route2),
            Association.create(
                parent_document=self.route1, child_document=self.route3)
        ])
        self.session.flush()

        new_associations = {
            'routes': [
                {'document_id': self.route2.document_id, 'is_parent': True},
                {'document_id': self.route4.document_id, 'is_parent': True}
            ],
            'waypoints': [
                {'document_id': self.waypoint1.document_id, 'is_parent': True}
            ]
        }
        synchronize_associations(
            self.route1, new_associations, self.global_userids['contributor'])

        self.assertIsNotNone(self._get_association(self.route1, self.route2))
        self.assertIsNotNone(self._get_association(self.route4, self.route1))
        self.assertIsNone(self._get_association(self.route2, self.route1))
        self.assertIsNone(self._get_association(self.route1, self.route3))
        self.assertIsNotNone(
            self._get_association(self.waypoint1, self.route1))

    def _get_association(self, main_doc, child_doc):
        return self.session.query(Association).get(
            (main_doc.document_id, child_doc.document_id))


def _get_document_ids(docs):
    return {d['document_id'] for d in docs}
