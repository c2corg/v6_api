import datetime

from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.article import Article
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OUTING_TYPE
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests.views import BaseTestRest


class TestAssociationRest(BaseTestRest):

    prefix = '/associations'

    def setUp(self):  # noqa
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_add_association_unauthorized(self):
        self.app_post_json(TestAssociationRest.prefix, {}, status=403)

    def test_add_association(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
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

        self.assertNotifiedEs()

        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.waypoint2.document_id, 2)

    def test_add_association_wa(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        association = self.session.query(Association).get(
            (self.waypoint1.document_id, self.article1.document_id))
        self.assertIsNotNone(association)

        association_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.article1.document_id). \
            one()
        self.assertEqual(association_log.is_creation, True)
        self.assertIsNotNone(association_log.user_id)

        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.article1.document_id, 2)

    def test_add_association_uo(self):
        contributor2 = self.global_userids['contributor2']
        request_body = {
            'parent_document_id': contributor2,
            'child_document_id': self.outing.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        association = self.session.query(Association).get(
            (contributor2, self.outing.document_id))
        self.assertIsNotNone(association)

        # check that the feed change is updated
        feed_change = self.get_feed_change(self.outing.document_id)
        self.assertIsNotNone(feed_change)
        self.assertEqual(feed_change.change_type, 'updated')
        self.assertEqual(
            feed_change.user_ids,
            [self.global_userids['contributor'],
             self.global_userids['contributor2']])

    def test_add_association_duplicate(self):
        """ Test that there is only one association between two documents.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')

        # first association, ok
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        # 2nd association, fail
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        # back-link association also fails
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.waypoint1.document_id
        }
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

    def test_add_association_invalid(self):
        request_body = {
            'parent_document_id': self.route1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
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
        response = self.app_post_json(
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

    def test_add_association_no_es_update(self):
        """Tests that the search index is only updated for specific association
        types.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        self.assertNotNotifiedEs()

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
        self.app_post_json(
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

        self.assertNotifiedEs()

        self.check_cache_version(self.waypoint1.document_id, 3)
        self.check_cache_version(self.waypoint2.document_id, 3)

    def test_delete_association_fuzzy(self):
        """Test that an association {parent: x, child: y} can be
        deleted with {parent: y, child: x}.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='contributor')

        # add association
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        # then delete it again, but by switching parent/child id
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.waypoint1.document_id,
        }
        self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        association = self.session.query(Association).get(
            (self.waypoint1.document_id, self.waypoint2.document_id))
        self.assertIsNone(association)

    def test_delete_association_main_waypoint(self):
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.route1.document_id
        }
        headers = self.add_authorization_header(username='contributor')

        # add association
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

        # make the wp the main waypoint of the route
        self.route1.main_waypoint_id = self.waypoint2.document_id
        self.session.flush()

        # then try to delete the association
        response = self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)

        self.assertEqual(errors[0].get('name'), 'Bad Request')
        self.assertEqual(
            errors[0].get('description'),
            'as the main waypoint of the route, this waypoint can not '
            'be disassociated')

    def _add_test_data(self):
        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)

        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=200)
        self.session.add(self.waypoint2)

        self.route1 = Route(activities=['skitouring'])
        self.session.add(self.route1)

        self.image1 = Image(filename='image.jpg')
        self.session.add(self.image1)

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='collab')
        self.session.add(self.article1)

        self.outing = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1)
        )
        self.session.add(self.outing)
        self.session.flush()

        user_id = self.global_userids['contributor']
        self.session.add(Association(
            parent_document_id=user_id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=self.outing.document_id,
            child_document_type=OUTING_TYPE))

        update_feed_document_create(self.outing, user_id)
        self.session.flush()
