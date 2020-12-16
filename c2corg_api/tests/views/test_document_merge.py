from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import DocumentGeometry, DocumentLocale, \
    UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import update_feed_document_create, DocumentChange
from c2corg_api.models.image import Image
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document import DocumentRest
from sqlalchemy.sql.expression import or_
from httmock import all_requests, HTTMock


class TestDocumentMergeRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestDocumentMergeRest, self).setUp()
        self._prefix = '/documents/merge'

        contributor_id = self.global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles')
            ])
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint2)
        self.session.flush()
        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=4985,
            redirects_to=self.waypoint1.document_id,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint3)
        self.waypoint4 = Waypoint(
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint4)
        self.session.flush()

        self.route1 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            main_waypoint_id=self.waypoint1.document_id,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route1)

        self.route2 = Route(
            activities=['skitouring'], elevation_max=1400, elevation_min=700,
            main_waypoint_id=self.waypoint1.document_id,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du soleil',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route2)
        self.session.flush()

        DocumentRest.create_new_version(self.waypoint1, contributor_id)
        update_feed_document_create(self.waypoint1, contributor_id)

        DocumentRest.create_new_version(self.route1, contributor_id)
        update_feed_document_create(self.route1, contributor_id)

        DocumentRest.create_new_version(self.route2, contributor_id)
        update_feed_document_create(self.route2, contributor_id)

        association = Association.create(
            parent_document=self.waypoint1,
            child_document=self.route1)
        self.session.add(association)
        self.session.add(association.get_log(
            self.global_userids['contributor']))

        association = Association.create(
            parent_document=self.waypoint1,
            child_document=self.route2)
        self.session.add(association)
        self.session.add(association.get_log(
            self.global_userids['contributor']))

        association = Association.create(
            parent_document=self.waypoint1,
            child_document=self.waypoint4)
        self.session.add(association)
        self.session.add(association.get_log(
            self.global_userids['contributor']))

        association = Association.create(
            parent_document=self.waypoint2,
            child_document=self.waypoint4)
        self.session.add(association)
        self.session.add(association.get_log(
            self.global_userids['contributor']))
        self.session.flush()

        self.image1 = Image(
            filename='image1.jpg',
            activities=['paragliding'], height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air',
                    description='...')])
        self.session.add(self.image1)

        self.image2 = Image(
            filename='image2.jpg',
            activities=['paragliding'], height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air',
                    description='...')])
        self.session.add(self.image2)

        self.session.flush()
        DocumentRest.create_new_version(self.image1, contributor_id)
        self.session.flush()

        self.image1.filename = 'image1.1.jpg'
        self.session.flush()
        DocumentRest.update_version(
            self.image1, contributor_id,
            'changed filename', [UpdateType.FIGURES], [])
        self.session.flush()

        self.session.add(DocumentTag(
            document_id=self.route1.document_id, document_type=ROUTE_TYPE,
            user_id=contributor_id))
        self.session.add(DocumentTagLog(
            document_id=self.route1.document_id, document_type=ROUTE_TYPE,
            user_id=contributor_id, is_creation=True))
        self.session.flush()

    def _post(self, body, expected_status):
        headers = self.add_authorization_header(username='moderator')
        return self.app_post_json(
            self._prefix, body, headers=headers, status=expected_status)

    def test_non_unauthorized(self):
        self.app_post_json(self._prefix, {}, status=403)

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(self._prefix, {}, headers=headers, status=403)

    def test_empty_body(self):
        self._post({}, 400)

    def test_same_document(self):
        self._post({
            'source_document_id': self.waypoint1.document_id,
            'target_document_id': self.waypoint1.document_id
        }, 400)

    def test_non_existing_documents(self):
        self._post({
            'source_document_id': -9999999,
            'target_document_id': -99999999
        }, 400)

    def test_not_same_types(self):
        self._post({
            'source_document_id': self.waypoint1.document_id,
            'target_document_id': self.route1.document_id
        }, 400)

    def test_already_merged(self):
        self._post({
            'source_document_id': self.waypoint3.document_id,
            'target_document_id': self.waypoint2.document_id
        }, 400)
        self._post({
            'source_document_id': self.waypoint2.document_id,
            'target_document_id': self.waypoint3.document_id
        }, 400)

    def test_merge_waypoint(self):
        self._post({
            'source_document_id': self.waypoint1.document_id,
            'target_document_id': self.waypoint2.document_id
        }, 200)

        # check that associations have been transferred
        association_count = self.session.query(Association).filter(or_(
            Association.parent_document_id == self.waypoint1.document_id,
            Association.child_document_id == self.waypoint1.document_id
        )).count()
        self.assertEqual(0, association_count)
        association_log_count = self.session.query(AssociationLog).filter(or_(
            AssociationLog.parent_document_id == self.waypoint1.document_id,
            AssociationLog.child_document_id == self.waypoint1.document_id
        )).count()
        self.assertEqual(0, association_count)
        self.assertEqual(0, association_log_count)

        association_route = self.session.query(Association).get(
            (self.waypoint2.document_id, self.route1.document_id))
        self.assertIsNotNone(association_route)

        # check that main waypoints are transferred
        self.session.refresh(self.route1)
        self.assertEqual(
            self.route1.main_waypoint_id, self.waypoint2.document_id)
        route_locale = self.route1.locales[0]
        self.assertEqual('Mont Blanc', route_locale.title_prefix)

        # check that the redirection is set
        self.session.refresh(self.waypoint1)
        self.assertEqual(
            self.waypoint1.redirects_to, self.waypoint2.document_id
        )

        # check that a new version was created for the source document
        new_source_version = self.session.query(DocumentVersion). \
            filter(
                DocumentVersion.document_id == self.waypoint1.document_id). \
            order_by(DocumentVersion.id.desc()). \
            first()
        self.assertIsNotNone(new_source_version)
        self.assertEqual(
            'merged with {}'.format(self.waypoint2.document_id),
            new_source_version.history_metadata.comment
        )

        # check that the cache versions are updated
        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.waypoint2.document_id, 3)
        self.check_cache_version(self.route1.document_id, 2)

        # check that the feed entry is removed
        feed_count = self.session.query(DocumentChange).filter(
            DocumentChange.document_id == self.waypoint1.document_id
        ).count()
        self.assertEqual(0, feed_count)

    def test_merge_image(self):
        call = {'times': 0}

        @all_requests
        def image_service_mock(url, request):
            call['times'] += 1
            call['request.body'] = request.body.split('&')
            call['request.url'] = request.url
            return {
                'status_code': 200,
                'content': ''
            }

        with HTTMock(image_service_mock):
            self._post({
                'source_document_id': self.image1.document_id,
                'target_document_id': self.image2.document_id
            }, 200)
            self.assertEqual(call['times'], 1)
            self.assertIn('filenames=image1.1.jpg', call['request.body'])
            self.assertIn('filenames=image1.jpg', call['request.body'])
            self.assertEqual(
                call['request.url'],
                self.settings['image_backend.url'] + '/delete')

    def test_merge_image_error_deleting_files(self):
        """ Test that the merge request is also successful if the image files
        cannot be deleted.
        """
        call = {'times': 0}

        @all_requests
        def image_service_mock(url, request):
            call['times'] += 1
            call['request.body'] = request.body.split('&')
            call['request.url'] = request.url
            return {
                'status_code': 500,
                'content': 'some random error'
            }

        with HTTMock(image_service_mock):
            self._post({
                'source_document_id': self.image1.document_id,
                'target_document_id': self.image2.document_id
            }, 200)
            self.assertEqual(call['times'], 1)
            self.assertIn('filenames=image1.1.jpg', call['request.body'])
            self.assertIn('filenames=image1.jpg', call['request.body'])
            self.assertEqual(
                call['request.url'],
                self.settings['image_backend.url'] + '/delete')

    def test_tags(self):
        self._post({
            'source_document_id': self.route1.document_id,
            'target_document_id': self.route2.document_id
        }, 200)

        # Check tags and logs have been transfered from route1 to route2
        count = self.session.query(DocumentTag). \
            filter(DocumentTag.document_id == self.route2.document_id). \
            count()
        self.assertEqual(count, 1)
        count = self.session.query(DocumentTagLog). \
            filter(DocumentTagLog.document_id == self.route2.document_id). \
            count()
        self.assertEqual(count, 1)
