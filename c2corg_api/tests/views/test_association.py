import datetime

from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.article import Article
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OUTING_TYPE
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document import DocumentRest


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
        feed_change = self.get_feed_change(
            self.outing.document_id, change_type='updated')
        self.assertIsNotNone(feed_change)
        self.assertEqual(feed_change.change_type, 'updated')
        self.assertEqual(
            set(feed_change.user_ids),
            set([
                self.global_userids['contributor'],
                self.global_userids['contributor2']]))

        # check that the participants of the 2nd feed change are also updated
        feed_change = self.get_feed_change(
            self.outing.document_id, change_type='added_photos')
        self.assertIsNotNone(feed_change)
        self.assertEqual(
            set(feed_change.user_ids),
            set([
                self.global_userids['contributor'],
                self.global_userids['contributor2'],
                self.global_userids['moderator']]))

    def test_add_association_uo_no_rights(self):
        """ Check that associations with outings can only be changed by users
        associated to the outing or moderators.
        """
        contributor2 = self.global_userids['contributor2']
        request_body = {
            'parent_document_id': contributor2,
            'child_document_id': self.outing.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.outings',
            'no rights to modify associations with outing {}'.format(
                self.outing.document_id))

    def test_add_association_wc_article_collab(self):
        """ Check that associations with articles can only be changed by
        everyone.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

    def test_add_association_wc_article_personal_unauthorized(self):
        """ Check that associations with personal articles can only be changed
        by the creator and moderators.
        """
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.articles',
            'no rights to modify associations with article {}'.format(
                self.article1.document_id))

    def test_add_association_wc_article_personal_authorized(self):
        """ Check that associations with personal articles can only be changed
        by the creator and moderators.
        """
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

    def test_add_association_cc_article_personal_unauthorized(self):
        """ Check that associations with personal articles can only be changed
        by the creator and moderators.
        """
        request_body = {
            'parent_document_id': self.article2.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.articles',
            'no rights to modify associations with article {}'.format(
                self.article2.document_id))

    def test_add_association_wi_image_personal_unauthorized(self):
        """ Check that associations with personal images can only be changed
        by the creator and moderators.
        """
        self.image1.image_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.images',
            'no rights to modify associations with image {}'.format(
                self.image1.document_id))

    def test_add_association_wi_image_personal_authorized(self):
        """ Check that associations with personal images can only be changed
        by the creator and moderators.
        """
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

    def test_add_association_wx_xreport_unauthorized(self):
        """ Check that associations with x-reports can only be changed
        by the creator and moderators.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.report1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.xreports',
            'no rights to modify associations with xreport {}'.format(
                self.report1.document_id))

    def test_add_association_wx_xreport_authorized(self):
        """ Check that associations with x-reports can only be changed
        by the creator and moderators.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.report1.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=200)

    def test_add_association_wc_xreport_article_unauthorized(self):
        """ Check an association between a xreport and article that both
        do not accept associations from contributor2.
        """
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.report1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'associations.xreports',
            'no rights to modify associations with xreport {}'.format(
                self.report1.document_id))
        self.assertError(
            body['errors'], 'associations.articles',
            'no rights to modify associations with article {}'.format(
                self.article1.document_id))

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

    def test_add_association_redirected_document(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint3.document_id,
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)

        self.assertEqual(errors[0].get('name'), 'child_document_id')
        self.assertEqual(
            errors[0].get('description'),
            'child document does not exist or is redirected')

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
            errors[0].get('description'),
            'parent document does not exist or is redirected')

        self.assertEqual(errors[1].get('name'), 'child_document_id')
        self.assertEqual(
            errors[1].get('description'),
            'child document does not exist or is redirected')

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
        headers = self.add_authorization_header(username='moderator')

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

    def test_delete_association_non_moderator(self):
        """ For non-personal documents, a normal user can create associations
        but not delete them.
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

        # then try to delete it again
        response = self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'Bad Request',
            'no rights to modify associations between document '
            'w ({}) and w ({})'.format(
                self.waypoint1.document_id, self.waypoint2.document_id))

    def test_delete_association_fuzzy(self):
        """Test that an association {parent: x, child: y} can be
        deleted with {parent: y, child: x}.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self.add_authorization_header(username='moderator')

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

    def test_delete_association_uo(self):
        contributor2 = self.global_userids['contributor2']
        request_body = {
            'parent_document_id': contributor2,
            'child_document_id': self.outing.document_id,
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

    def test_delete_association_uo_no_rights(self):
        """ Try to delete an association to an outing with a user that has
        no permission to change this outing.
        """
        request_body = {
            'parent_document_id': self.global_userids['contributor'],
            'child_document_id': self.outing.document_id,
        }

        headers = self.add_authorization_header(username='contributor2')
        self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers,
            status=400)

    def test_delete_association_wc_article_personal(self):
        """ Test that associations with personal articles require special
        rights.
        """
        self.article1.article_type = 'personal'
        self.session.flush()

        # first create an association with the article
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        headers1 = self.add_authorization_header(username='contributor')
        self.app_post_json(
            TestAssociationRest.prefix, request_body, headers=headers1,
            status=200)

        # then try to delete the association again with a different user
        headers2 = self.add_authorization_header(username='contributor2')
        response = self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers2,
            status=400)
        body = response.json

        self.assertError(
            body['errors'], 'Bad Request',
            'no rights to modify associations between document '
            'w ({}) and c ({})'.format(
                self.waypoint1.document_id, self.article1.document_id))

        # but the original user can delete it
        self.app.delete_json(
            TestAssociationRest.prefix, request_body, headers=headers1,
            status=200)

    def test_delete_association_wp_r_last_waypoint(self):
        request_body1 = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.route1.document_id
        }
        headers = self.add_authorization_header(username='moderator')

        # add association
        self.app_post_json(
            TestAssociationRest.prefix, request_body1, headers=headers,
            status=200)

        # try to delete the association
        response = self.app.delete_json(
            TestAssociationRest.prefix, request_body1, headers=headers,
            status=400)

        body = response.json
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertError(
            errors, 'Bad Request',
            'as the last waypoint of the route, this waypoint can not be '
            'disassociated')

        # add a second waypoint
        request_body2 = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.route1.document_id
        }
        self.app_post_json(
            TestAssociationRest.prefix, request_body2, headers=headers,
            status=200)

        # now, the first waypoint can be unlinked
        self.app.delete_json(
            TestAssociationRest.prefix, request_body1, headers=headers)

    def test_delete_association_ro_last_route(self):
        request_body1 = {
            'parent_document_id': self.route1.document_id,
            'child_document_id': self.outing.document_id
        }
        headers = self.add_authorization_header(username='moderator')

        # add association
        self.app_post_json(
            TestAssociationRest.prefix, request_body1, headers=headers,
            status=200)

        # try to delete the association
        response = self.app.delete_json(
            TestAssociationRest.prefix, request_body1, headers=headers,
            status=400)

        body = response.json
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertError(
            errors, 'Bad Request',
            'as the last route of the outing, this route can not be '
            'disassociated')

        # add a second route
        request_body2 = {
            'parent_document_id': self.route2.document_id,
            'child_document_id': self.outing.document_id
        }
        self.app_post_json(
            TestAssociationRest.prefix, request_body2, headers=headers,
            status=200)

        # now, the first route can be unlinked
        self.app.delete_json(
            TestAssociationRest.prefix, request_body1, headers=headers)

    def _add_test_data(self):
        user_id = self.global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)

        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=200)
        self.session.add(self.waypoint2)
        self.session.flush()

        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=200,
            redirects_to=self.waypoint1.document_id)
        self.session.add(self.waypoint3)

        self.route1 = Route(activities=['skitouring'])
        self.session.add(self.route1)
        self.session.add(self.waypoint2)

        self.route2 = Route(activities=['skitouring'])
        self.session.add(self.route2)

        self.image1 = Image(
            filename='image.jpg',
            locales=[
                DocumentLocale(lang='en', title='Mont Blanc from the air')])
        self.session.add(self.image1)
        self.session.flush()
        DocumentRest.create_new_version(self.image1, user_id)

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='collab',
            locales=[DocumentLocale(lang='en', title='Lac d\'Annecy')])
        self.session.add(self.article1)
        self.session.flush()
        DocumentRest.create_new_version(self.article1, user_id)

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='personal',
            locales=[DocumentLocale(lang='en', title='Lac d\'Annecy')])
        self.session.add(self.article2)
        self.session.flush()
        DocumentRest.create_new_version(self.article2, user_id)

        self.report1 = Xreport(
            event_activity='alpine_climbing',
            locales=[XreportLocale(lang='en', title='Lac d\'Annecy')])
        self.session.add(self.report1)
        self.session.flush()
        DocumentRest.create_new_version(self.report1, user_id)

        self.outing = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1)
        )
        self.session.add(self.outing)
        self.session.flush()

        self.session.add(Association(
            parent_document_id=user_id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=self.outing.document_id,
            child_document_type=OUTING_TYPE))

        update_feed_document_create(self.outing, user_id)
        self.session.flush()

        # create a 2nd feed entry for the outing
        feed_change = self.get_feed_change(self.outing.document_id)
        user_id = self.global_userids['moderator']
        feed_change2 = feed_change.copy()
        feed_change2.change_type = 'added_photos'
        feed_change2.user_id = user_id
        feed_change2.user_ids = list(
            set(feed_change.user_ids).union([user_id]))
        self.session.add(feed_change2)
        self.session.flush()
