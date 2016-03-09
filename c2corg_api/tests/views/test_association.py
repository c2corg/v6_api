from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests.views import BaseTestRest


class TestAssociationRest(BaseTestRest):

    prefix = '/associations'

    def setUp(self):  # noqa
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_add_association_unauthorized(self):
        self.app.post_json(TestAssociationRest.prefix, {}, status=403)

    def test_add_association(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        association = self.session.query(Association).get(
            (self.waypoint1.document_id, self.waypoint2.document_id))
        self.assertIsNotNone(association)

        association_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.waypoint2.document_id). \
            one()
        self.assertEqual(association_log.is_creation, True)
        self.assertIsNotNone(association_log.user_id)

    def test_add_association_duplicate(self):
        """ Test that there is only one association between two documents.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')

        # first association, ok
        self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        # 2nd association, fail
        self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        # back-link association also fails
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.waypoint1.document_id
        }
        self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

    def test_add_association_invalid(self):
        request_body = {
            'parent_document_id': self.route1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)

        self.assertEqual(errors[0].get('name'), 'association')
        self.assertEqual(
            errors[0].get('description'), 'invalid association type')

    def test_add_association_invalid_ids(self):
        request_body = {
            'parent_document_id': -99,
            'child_document_id': -999,
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)

        self.assertEqual(errors[0].get('name'), 'parent_document_id')
        self.assertEqual(
            errors[0].get('description'), 'parent document does not exist')

        self.assertEqual(errors[1].get('name'), 'child_document_id')
        self.assertEqual(
            errors[1].get('description'), 'child document does not exist')

    def test_delete_association_unauthorized(self):
        self.app.delete_json(TestAssociationRest.prefix, {}, status=403)

    def test_delete_association_not_existing(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')

        self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

    def test_delete_association(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')

        # add association
        self.app.post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        # then delete it again
        self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        association = self.session.query(Association).get(
            (self.waypoint1.document_id, self.waypoint2.document_id))
        self.assertIsNone(association)

        logs = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.waypoint2.document_id). \
            order_by(AssociationLog.written_at). \
            all()
        self.assertEqual(logs[0].is_creation, True)
        self.assertEqual(logs[1].is_creation, False)

    def _add_test_data(self):
        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)

        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=200)
        self.session.add(self.waypoint2)

        self.route1 = Route(activities=['skitouring'])
        self.session.add(self.route1)
        self.session.flush()
