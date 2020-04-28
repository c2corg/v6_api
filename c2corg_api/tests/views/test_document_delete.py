import datetime

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import Article, ArchiveArticle
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import Book, ArchiveBook
from c2corg_api.models.document import (
    Document, DocumentLocale, DocumentGeometry, ArchiveDocument,
    ArchiveDocumentLocale, ArchiveDocumentGeometry, UpdateType,
    get_available_langs)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import (
    DocumentChange, update_feed_document_create, update_feed_images_upload)
from c2corg_api.models.image import Image, ArchiveImage
from c2corg_api.models.outing import (
    Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)
from c2corg_api.models.route import (
    Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)
from c2corg_api.models.xreport import (
    Xreport, XreportLocale, ArchiveXreport, ArchiveXreportLocale)
from c2corg_api.views.document import DocumentRest
from c2corg_api.tests.views import BaseTestRest
from sqlalchemy.sql.expression import or_
from httmock import all_requests, HTTMock


class TestDocumentDeleteRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestDocumentDeleteRest, self).setUp()
        self._prefix = '/documents/delete/'

        user_id = self.global_userids['contributor']

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
                    document_topic=DocumentTopic(topic_id=1),
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint2)

        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=3,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint3.locales.append(WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep', document_topic=DocumentTopic(topic_id=2)))
        self.waypoint3.locales.append(WaypointLocale(
            lang='fr', title='Mont Granier', description='...',
            access='ouai', document_topic=DocumentTopic(topic_id=3)))
        self.session.add(self.waypoint3)
        self.session.flush()

        self.waypoint4 = Waypoint(
            waypoint_type='summit', elevation=3,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint4.locales.append(WaypointLocale(
            lang='en', title='Mont Ventoux', description='...'))
        self.session.add(self.waypoint4)
        self.session.flush()

        DocumentRest.create_new_version(self.waypoint1, user_id)
        update_feed_document_create(self.waypoint1, user_id)
        DocumentRest.create_new_version(self.waypoint2, user_id)
        update_feed_document_create(self.waypoint2, user_id)
        DocumentRest.create_new_version(self.waypoint3, user_id)
        update_feed_document_create(self.waypoint3, user_id)
        DocumentRest.create_new_version(self.waypoint4, user_id)
        update_feed_document_create(self.waypoint4, user_id)
        self.session.flush()

        route1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.route1 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            main_waypoint_id=self.waypoint1.document_id,
            geometry=route1_geometry
        )
        self.route1.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            title_prefix='Mont Blanc :', gear='paraglider'))
        self.session.add(self.route1)

        route2_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.route2 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            geometry=route2_geometry
        )
        self.route2.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            title_prefix='Mont Blanc :', gear='paraglider',
            document_topic=DocumentTopic(topic_id=4)))
        self.session.add(self.route2)
        self.session.flush()

        self._add_association(self.waypoint1, self.route1)
        self._add_association(self.waypoint2, self.route2)
        self.session.flush()

        route3_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.route3 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            geometry=route3_geometry
        )
        self.route3.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            title_prefix='Mont Blanc :', gear='paraglider',
            document_topic=DocumentTopic(topic_id=5)))
        self.session.add(self.route3)
        self.session.flush()

        DocumentRest.create_new_version(self.route1, user_id)
        update_feed_document_create(self.route1, user_id)
        DocumentRest.create_new_version(self.route2, user_id)
        update_feed_document_create(self.route2, user_id)
        DocumentRest.create_new_version(self.route3, user_id)
        update_feed_document_create(self.route3, user_id)

        self._add_association(self.waypoint1, self.route3)
        self._add_association(self.waypoint2, self.route3)
        self._add_association(self.waypoint3, self.route3)
        self._add_tag(self.route3)
        self.session.flush()

        outing1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.outing1 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing1_geometry,
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny', document_topic=DocumentTopic(topic_id=6))
            ]
        )
        self.session.add(self.outing1)
        self.session.flush()

        DocumentRest.create_new_version(self.outing1, user_id)
        update_feed_document_create(self.outing1, user_id)
        self._add_association(self.route1, self.outing1)
        self.session.flush()

        outing1b_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.outing1b = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing1b_geometry,
            redirects_to=self.outing1.document_id,
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny')
            ]
        )
        self.session.add(self.outing1b)
        self.session.flush()

        DocumentRest.create_new_version(self.outing1b, user_id)
        self.session.flush()

        outing2_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)')
        self.outing2 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing2_geometry,
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny', document_topic=DocumentTopic(topic_id=7))
            ]
        )
        self.session.add(self.outing2)
        self.session.flush()

        DocumentRest.create_new_version(self.outing2, user_id)
        update_feed_document_create(self.outing2, user_id)
        self._add_association(self.route2, self.outing2)
        self._add_association(self.route3, self.outing2)
        self.session.flush()

        self.article1 = Article(
            activities=['skitouring'], categories=['gear'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    lang='en', title='Some article',
                    description='Some content',
                    document_topic=DocumentTopic(topic_id=8))
            ]
        )
        self.session.add(self.article1)
        self.session.flush()

        DocumentRest.create_new_version(self.article1, user_id)
        update_feed_document_create(self.article1, user_id)
        self.session.flush()

        self.article1.locales[0].title = 'Some other article title'
        article1_lang = self.article1.locales[0].lang
        self.session.flush()
        DocumentRest.update_version(
            self.article1, user_id,
            'new title', [UpdateType.LANG], [article1_lang])
        self.session.flush()

        self._add_association(self.route2, self.article1)
        self._add_association(self.outing2, self.article1)
        self.session.flush()

        self.article2 = Article(
            activities=['skitouring'], categories=['gear'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    lang='en', title='Some other article',
                    description='Some content')
            ]
        )
        self.session.add(self.article2)
        self.session.flush()

        # Make the article older than 24h old
        written_at = datetime.datetime(2016, 1, 1, 0, 0, 0)
        DocumentRest.create_new_version(self.article2, user_id, written_at)
        update_feed_document_create(self.article2, user_id)
        self.session.flush()

        self.book1 = Book(
            activities=['skitouring'], book_types=['biography'],
            locales=[
                DocumentLocale(
                    lang='en', title='Some book',
                    description='Some content',
                    document_topic=DocumentTopic(topic_id=9))
            ]
        )
        self.session.add(self.book1)
        self.session.flush()

        DocumentRest.create_new_version(self.book1, user_id)
        update_feed_document_create(self.book1, user_id)
        self._add_association(self.book1, self.route2)
        self._add_association(self.book1, self.route3)
        self.session.flush()

        self.xreport1 = Xreport(
            event_activity='alpine_climbing', event_type='stone_ice_fall',
            locales=[
                XreportLocale(
                    lang='en', title='Lac d\'Annecy',
                    place='some place descrip. in english',
                    document_topic=DocumentTopic(topic_id=10)),
                XreportLocale(
                    lang='fr', title='Lac d\'Annecy',
                    place='some place descrip. in french',
                    document_topic=DocumentTopic(topic_id=11))
            ]
        )
        self.session.add(self.xreport1)
        self.session.flush()

        DocumentRest.create_new_version(self.xreport1, user_id)
        update_feed_document_create(self.xreport1, user_id)
        self._add_association(self.outing2, self.xreport1)
        self._add_association(self.route3, self.xreport1)
        self.session.flush()

        self.image1 = Image(
            filename='image1.jpg',
            activities=['paragliding'], height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air',
                    description='...',
                    document_topic=DocumentTopic(topic_id=12))])
        self.session.add(self.image1)
        self.session.flush()

        DocumentRest.create_new_version(self.image1, user_id)
        self._add_association(self.outing1, self.image1)
        self._add_association(self.route3, self.image1)
        self._add_association(self.waypoint3, self.image1)
        self.session.flush()

        update_feed_images_upload(
            [self.image1],
            [{
                'filename': 'image1.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air'}
                ],
                'associations': {
                    'outings': [{'document_id': self.outing1.document_id}],
                    'routes': [{'document_id': self.route3.document_id}],
                    'waypoints': [{'document_id': self.waypoint3.document_id}]
                }
            }],
            user_id)

        self.image1.filename = 'image1.1.jpg'
        self.session.flush()
        DocumentRest.update_version(
            self.image1, user_id,
            'changed filename', [UpdateType.FIGURES], [])
        self.session.flush()

        self.topo_map1 = TopoMap(
            code='3232ET', editor='IGN', scale='25000',
            locales=[
                DocumentLocale(lang='fr', title='Belley')
            ],
            geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))')  # noqa
        )
        self.session.add(self.topo_map1)
        self.session.flush()
        self.session.add(TopoMapAssociation(
            document=self.waypoint2, topo_map=self.topo_map1))
        self.session.add(TopoMapAssociation(
            document=self.waypoint3, topo_map=self.topo_map1))
        self.session.add(TopoMapAssociation(
            document=self.route2, topo_map=self.topo_map1))
        self.session.add(TopoMapAssociation(
            document=self.route3, topo_map=self.topo_map1))
        self.session.flush()

        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            )
        )
        self.session.add(self.area1)
        self.session.flush()
        self.session.add(AreaAssociation(
            document=self.waypoint2, area=self.area1))
        self.session.add(AreaAssociation(
            document=self.waypoint3, area=self.area1))
        self.session.add(AreaAssociation(
            document=self.route2, area=self.area1))
        self.session.add(AreaAssociation(
            document=self.route3, area=self.area1))
        self.session.flush()

    def _add_association(self, parent_document, child_document):
        association = Association.create(
            parent_document=parent_document,
            child_document=child_document)
        self.session.add(association)
        self.session.add(association.get_log(
            self.global_userids['contributor']))

    def _add_tag(self, document):
        document_id = document.document_id
        document_type = document.type
        user_id = self.global_userids['contributor']
        tag = DocumentTag(
            document_id=document_id, document_type=document_type,
            user_id=user_id)
        self.session.add(tag)
        log = DocumentTagLog(
            document_id=document_id, document_type=document_type,
            user_id=user_id, is_creation=True)
        self.session.add(log)

    def _delete(self, document_id, expected_status):
        headers = self.add_authorization_header(username='moderator')
        return self.app.delete_json(
            self._prefix + str(document_id),
            headers=headers, status=expected_status)

    def test_non_unauthorized(self):
        self.app.delete_json(
            self._prefix + str(self.waypoint1.document_id), {}, status=403)

    def test_delete_non_existing_document(self):
        self._delete(-9999999, 400)

    def test_delete_main_waypoint(self):
        """ Test that a main waypoint cannot be deleted.
        """
        response = self._delete(self.waypoint1.document_id, 400)
        self.assertErrorsContain(
            response.json, 'document_id',
            'This waypoint cannot be deleted because it is a main waypoint.')

    def test_delete_former_main_waypoint(self):
        """ Test that a former main waypoint can be deleted.
        """
        self.route3.main_waypoint_id = self.waypoint3.document_id
        self.session.flush()
        DocumentRest.update_version(self.route3,
                                    self.global_userids['contributor'],
                                    'Update',
                                    [UpdateType.FIGURES],
                                    [])

        self.route3.main_waypoint_id = self.waypoint1.document_id
        self.session.flush()
        DocumentRest.update_version(self.route3,
                                    self.global_userids['contributor'],
                                    'Update',
                                    [UpdateType.FIGURES],
                                    [])

        self._delete(self.waypoint3.document_id, 200)

    def test_delete_only_waypoint_of_route(self):
        """ Test that the only waypoint of a route cannot be deleted.
        """
        response = self._delete(self.waypoint2.document_id, 400)
        self.assertErrorsContain(
            response.json, 'document_id',
            'This waypoint cannot be deleted because '
            'it is the only waypoint associated to some routes.')

    def test_delete_only_route_of_outing(self):
        """ Test that a route cannot be deleted if it is the only route
            of some outing."""
        response = self._delete(self.route1.document_id, 400)
        self.assertErrorsContain(
            response.json, 'document_id',
            'This route cannot be deleted because '
            'it is the only route associated to some outings.')

    def _test_delete(
            self, document_id, clazz, clazz_locale, archive_clazz,
            archive_clazz_locale, expected_deleted_docs_count=1):

        # Get the number of documents before deleting
        initial_count = self.session.query(clazz).count()
        initial_doc_count = self.session.query(Document).count()

        self._delete(document_id, 200)

        # Check that only one document has been deleted
        count = self.session.query(clazz).count()
        self.assertEqual(initial_count - count, expected_deleted_docs_count)
        count = self.session.query(Document).count()
        self.assertEqual(
            initial_doc_count - count, expected_deleted_docs_count)

        # Check that the document versions table is cleared
        count = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id).count()
        self.assertEqual(0, count)

        # Check that entries have been removed in the main tables
        count = self.session.query(clazz). \
            filter(getattr(clazz, 'document_id') == document_id).count()
        self.assertEqual(0, count)
        count = self.session.query(Document). \
            filter(Document.document_id == document_id).count()
        self.assertEqual(0, count)
        if clazz_locale:
            count = self.session.query(clazz_locale). \
                filter(getattr(clazz_locale, 'document_id') == document_id). \
                count()
            self.assertEqual(0, count)
        count = self.session.query(DocumentLocale). \
            filter(DocumentLocale.document_id == document_id).count()
        self.assertEqual(0, count)
        count = self.session.query(DocumentGeometry). \
            filter(DocumentGeometry.document_id == document_id).count()
        self.assertEqual(0, count)

        # Check the archives have been cleared too
        count = self.session.query(archive_clazz). \
            filter(getattr(archive_clazz, 'document_id') == document_id). \
            count()
        self.assertEqual(0, count)
        count = self.session.query(ArchiveDocument). \
            filter(ArchiveDocument.document_id == document_id).count()
        self.assertEqual(0, count)
        if archive_clazz_locale:
            count = self.session.query(archive_clazz_locale). \
                filter(getattr(
                    archive_clazz_locale, 'document_id') == document_id). \
                count()
            self.assertEqual(0, count)
        count = self.session.query(ArchiveDocumentLocale). \
            filter(ArchiveDocumentLocale.document_id == document_id).count()
        self.assertEqual(0, count)
        count = self.session.query(ArchiveDocumentGeometry). \
            filter(ArchiveDocumentGeometry.document_id == document_id).count()
        self.assertEqual(0, count)

        # check associations have been cleared
        association_count = self.session.query(Association).filter(or_(
            Association.parent_document_id == document_id,
            Association.child_document_id == document_id
        )).count()
        self.assertEqual(0, association_count)
        association_log_count = self.session.query(AssociationLog).filter(or_(
            AssociationLog.parent_document_id == document_id,
            AssociationLog.child_document_id == document_id
        )).count()
        self.assertEqual(0, association_log_count)
        association_count = self.session.query(TopoMapAssociation).filter(
            TopoMapAssociation.document_id == document_id).count()
        self.assertEqual(0, association_count)
        association_count = self.session.query(AreaAssociation).filter(
            AreaAssociation.document_id == document_id).count()
        self.assertEqual(0, association_count)

        # Check the feed has been cleared
        feed_count = self.session.query(DocumentChange).filter(
            DocumentChange.document_id == document_id
        ).count()
        self.assertEqual(0, feed_count)

    def test_delete_waypoint(self):
        self._test_delete(
            self.waypoint3.document_id,
            Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route3.document_id, 2)
        self.check_cache_version(self.image1.document_id, 2)

    def test_delete_route(self):
        self._test_delete(
            self.route3.document_id,
            Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.waypoint1.document_id, 3)
        self.check_cache_version(self.waypoint2.document_id, 3)
        self.check_cache_version(self.waypoint3.document_id, 3)
        self.check_cache_version(self.outing2.document_id, 2)
        self.check_cache_version(self.book1.document_id, 2)
        self.check_cache_version(self.xreport1.document_id, 2)
        self.check_cache_version(self.image1.document_id, 2)

    def _count_tags(self, document_id):
        nb_tags = self.session.query(DocumentTag). \
            filter(DocumentTag.document_id == document_id).count()
        nb_logs = self.session.query(DocumentTagLog). \
            filter(DocumentTagLog.document_id == document_id).count()
        return nb_tags, nb_logs

    def test_delete_route_with_tags(self):
        nb_tags, nb_logs = self._count_tags(self.route3.document_id)
        self.assertEqual(nb_tags, 1)
        self.assertEqual(nb_logs, 1)

        self._test_delete(
            self.route3.document_id,
            Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)

        # Check related tags have been removed
        nb_tags, nb_logs = self._count_tags(self.route3.document_id)
        self.assertEqual(nb_tags, 0)
        self.assertEqual(nb_logs, 0)

    def test_delete_outing(self):
        # outing1b redirects to outing1 => 2 documents to delete
        self._test_delete(
            self.outing1.document_id,
            Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale, 2)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route1.document_id, 2)
        self.check_cache_version(self.image1.document_id, 2)

    def test_delete_outing_route_waypoint(self):
        self._test_delete(
            self.outing2.document_id,
            Outing, OutingLocale, ArchiveOuting, ArchiveOutingLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route2.document_id, 2)
        self.check_cache_version(self.route3.document_id, 2)
        self.check_cache_version(self.article1.document_id, 2)
        self.check_cache_version(self.xreport1.document_id, 2)

        self._test_delete(
            self.route2.document_id,
            Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.waypoint2.document_id, 4)
        self.check_cache_version(self.article1.document_id, 3)
        self.check_cache_version(self.book1.document_id, 2)

        self._test_delete(
            self.waypoint2.document_id,
            Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route3.document_id, 3)

    def test_delete_article(self):
        self._test_delete(
            self.article1.document_id, Article, None, ArchiveArticle, None)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route2.document_id, 2)
        self.check_cache_version(self.outing2.document_id, 2)

    def test_delete_book(self):
        self._test_delete(
            self.book1.document_id, Book, None, ArchiveBook, None)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route2.document_id, 2)
        self.check_cache_version(self.route3.document_id, 2)

    def test_delete_xreport(self):
        self._test_delete(
            self.xreport1.document_id,
            Xreport, XreportLocale, ArchiveXreport, ArchiveXreportLocale)

        # Check that associated documents cache versions have been incremented
        self.check_cache_version(self.route3.document_id, 2)
        self.check_cache_version(self.outing2.document_id, 2)

    def test_delete_image(self):
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
            self._test_delete(
                self.image1.document_id, Image, None, ArchiveImage, None)
            self.assertEqual(call['times'], 1)
            self.assertIn('filenames=image1.1.jpg', call['request.body'])
            self.assertIn('filenames=image1.jpg', call['request.body'])
            self.assertEqual(
                call['request.url'],
                self.settings['image_backend.url'] + '/delete')
            self.check_cache_version(self.waypoint3.document_id, 2)
            self.check_cache_version(self.route3.document_id, 2)
            self.check_cache_version(self.outing1.document_id, 2)

    def test_delete_image_error_deleting_files(self):
        """ Test that the delete request is also successful if the image files
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
                'content': ''
            }

        with HTTMock(image_service_mock):
            self._test_delete(
                self.image1.document_id, Image, None, ArchiveImage, None)
            self.assertEqual(call['times'], 1)
            self.assertIn('filenames=image1.1.jpg', call['request.body'])
            self.assertIn('filenames=image1.jpg', call['request.body'])
            self.assertEqual(
                call['request.url'],
                self.settings['image_backend.url'] + '/delete')
            self.check_cache_version(self.waypoint3.document_id, 2)
            self.check_cache_version(self.route3.document_id, 2)
            self.check_cache_version(self.outing1.document_id, 2)

    def test_delete_collaborative_doc(self):
        # Collaborative documents cannot be deleted, even by their authors:
        headers = self.add_authorization_header(username='contributor')
        return self.app.delete_json(
            self._prefix + str(self.waypoint4.document_id), {},
            headers=headers, status=400)

        # Moderators can:
        headers = self.add_authorization_header(username='moderator')
        return self.app.delete_json(
            self._prefix + str(self.waypoint4.document_id), {},
            headers=headers, status=200)

    def test_delete_personal_doc_not_author(self):
        # Personal documents cannot be deleted by anyone:
        headers = self.add_authorization_header(username='contributor2')
        return self.app.delete_json(
            self._prefix + str(self.article1.document_id), {},
            headers=headers, status=400)

        # Except by moderators:
        headers = self.add_authorization_header(username='moderator')
        return self.app.delete_json(
            self._prefix + str(self.article1.document_id), {},
            headers=headers, status=200)

    def test_delete_personal_doc_author_less_24h(self):
        # article1 has just been created by 'contributor'
        headers = self.add_authorization_header(username='contributor')
        return self.app.delete_json(
            self._prefix + str(self.article1.document_id), {},
            headers=headers, status=200)

    def test_delete_personal_doc_author_more_24h(self):
        # article2 is older than 24h
        headers = self.add_authorization_header(username='contributor')
        return self.app.delete_json(
            self._prefix + str(self.article2.document_id), {},
            headers=headers, status=400)

    def test_delete_locale_non_unauthorized(self):
        self.app.delete_json(
            self._prefix + str(self.waypoint1.document_id) + '/fr',
            {}, status=403)

        headers = self.add_authorization_header(username='contributor')
        return self.app.delete_json(
            self._prefix + str(self.waypoint1.document_id) + '/fr',
            {}, headers=headers, status=403)

    def _delete_locale(self, document_id, lang, expected_status):
        headers = self.add_authorization_header(username='moderator')
        return self.app.delete_json(
            self._prefix + str(document_id) + '/' + lang,
            headers=headers, status=expected_status)

    def test_delete_locale_non_existing_document(self):
        self._delete_locale(-9999999, 'fr', 400)

    def test_delete_locale_non_existing_locale(self):
        self._delete_locale(self.waypoint1.document_id, 'de', 400)

    def test_delete_locale_main_waypoint_with_only_one_locale(self):
        response = self._delete_locale(self.waypoint1.document_id, 'fr', 400)
        self.assertErrorsContain(
            response.json, 'document_id',
            'This waypoint cannot be deleted because it is a main waypoint.')

    def _test_delete_locale(self, document_id, lang):
        available_langs = get_available_langs(document_id)

        initial_other_locale_archives_count = self.session. \
            query(ArchiveDocumentLocale). \
            filter(ArchiveDocumentLocale.document_id == document_id). \
            filter(ArchiveDocumentLocale.lang != lang).count()

        initial_other_locale_versions_count = self.session. \
            query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang != lang).count()

        self._delete_locale(document_id, lang, 200)

        # Check that deleted locale is no longer available
        available_langs.remove(lang)
        final_available_langs = get_available_langs(document_id)
        # if the document had only one locale, it is deleted and
        # get_available_langs() returns None
        self.assertEqual(not final_available_langs, not available_langs)
        if available_langs:
            self.assertCountEqual(final_available_langs, available_langs)

        # Check that archives have been removed too
        count = self.session.query(ArchiveDocumentLocale). \
            filter(ArchiveDocumentLocale.document_id == document_id). \
            filter(ArchiveDocumentLocale.lang == lang).count()
        self.assertEqual(0, count)

        # but not other locale archives
        other_locale_archives_count = self.session. \
            query(ArchiveDocumentLocale). \
            filter(ArchiveDocumentLocale.document_id == document_id). \
            filter(ArchiveDocumentLocale.lang != lang).count()
        self.assertEqual(other_locale_archives_count,
                         initial_other_locale_archives_count)

        # Check that the document versions table is cleared
        count = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang == lang).count()
        self.assertEqual(0, count)

        # but not for other locales
        other_locale_versions_count = self.session. \
            query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang != lang).count()
        self.assertEqual(other_locale_versions_count,
                         initial_other_locale_versions_count)

        # Check the feed has been updated
        feed_items_langs = self.session.query(DocumentChange.langs).filter(
            DocumentChange.document_id == document_id
        ).all()
        for langs in feed_items_langs:
            self.assertNotIn(lang, langs)

    def test_delete_locale_waypoint(self):
        self._test_delete_locale(self.waypoint3.document_id, 'fr')

    def test_delete_locale_route_with_only_one_locale(self):
        document_id = self.route3.document_id
        self._test_delete_locale(document_id, 'en')

        # Test that the document has fully been deleted
        count = self.session.query(Document). \
            filter(Document.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(ArchiveDocument). \
            filter(ArchiveDocument.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(DocumentLocale). \
            filter(DocumentLocale.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(ArchiveDocumentLocale). \
            filter(ArchiveDocumentLocale.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(DocumentGeometry). \
            filter(DocumentGeometry.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(ArchiveDocumentGeometry). \
            filter(ArchiveDocumentGeometry.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id).count()
        self.assertEqual(count, 0)
        count = self.session.query(Association).filter(or_(
            Association.parent_document_id == document_id,
            Association.child_document_id == document_id
        )).count()
        self.assertEqual(count, 0)
