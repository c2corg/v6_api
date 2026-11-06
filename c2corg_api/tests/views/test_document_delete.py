import datetime
from collections import Counter

import pytest
from httmock import HTTMock, all_requests
from sqlalchemy.sql.expression import or_

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import ArchiveArticle, Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import ArchiveBook, Book
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
    UpdateType,
    get_available_langs,
)
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import (
    DocumentChange,
    update_feed_document_create,
    update_feed_images_upload,
)
from c2corg_api.models.image import ArchiveImage, Image
from c2corg_api.models.outing import (
    ArchiveOuting,
    ArchiveOutingLocale,
    Outing,
    OutingLocale,
)
from c2corg_api.models.route import ArchiveRoute, ArchiveRouteLocale, Route, RouteLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import (
    ArchiveWaypoint,
    ArchiveWaypointLocale,
    Waypoint,
    WaypointLocale,
)
from c2corg_api.models.xreport import (
    ArchiveXreport,
    ArchiveXreportLocale,
    Xreport,
    XreportLocale,
)
from c2corg_api.tests import assert_errors_contain, auth_headers
from c2corg_api.tests.views import scenarios
from c2corg_api.views.document import create_new_version, update_version


class TestDocumentDeleteRest:
    @pytest.fixture(autouse=True)
    def _setup_test_document_delete_rest(self, client, session, user_ids):
        self._prefix = '/documents/delete/'

        user_id = user_ids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles',
                )
            ],
        )
        session.add(self.waypoint1)

        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    document_topic=DocumentTopic(topic_id=1),
                    summary='The heighest point in Europe',
                )
            ],
        )
        session.add(self.waypoint2)

        self.waypoint3 = Waypoint(
            waypoint_type='summit',
            elevation=3,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint3.locales.append(
            WaypointLocale(
                lang='en',
                title='Mont Granier',
                description='...',
                access='yep',
                document_topic=DocumentTopic(topic_id=2),
            )
        )
        self.waypoint3.locales.append(
            WaypointLocale(
                lang='fr',
                title='Mont Granier',
                description='...',
                access='ouai',
                document_topic=DocumentTopic(topic_id=3),
            )
        )
        session.add(self.waypoint3)
        session.flush()

        self.waypoint4 = Waypoint(
            waypoint_type='summit',
            elevation=3,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint4.locales.append(
            WaypointLocale(lang='en', title='Mont Ventoux', description='...')
        )
        session.add(self.waypoint4)
        session.flush()

        create_new_version(self.waypoint1, user_id)
        update_feed_document_create(self.waypoint1, user_id)
        create_new_version(self.waypoint2, user_id)
        update_feed_document_create(self.waypoint2, user_id)
        create_new_version(self.waypoint3, user_id)
        update_feed_document_create(self.waypoint3, user_id)
        create_new_version(self.waypoint4, user_id)
        update_feed_document_create(self.waypoint4, user_id)
        session.flush()

        route1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.route1 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations='1',
            main_waypoint_id=self.waypoint1.document_id,
            geometry=route1_geometry,
        )
        self.route1.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
            )
        )
        session.add(self.route1)

        route2_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.route2 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations='1',
            geometry=route2_geometry,
        )
        self.route2.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
                document_topic=DocumentTopic(topic_id=4),
            )
        )
        session.add(self.route2)
        session.flush()

        self._add_association(session, user_ids, self.waypoint1, self.route1)
        self._add_association(session, user_ids, self.waypoint2, self.route2)
        session.flush()

        route3_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations='1',
            geometry=route3_geometry,
        )
        self.route3.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
                document_topic=DocumentTopic(topic_id=5),
            )
        )
        session.add(self.route3)
        session.flush()

        create_new_version(self.route1, user_id)
        update_feed_document_create(self.route1, user_id)
        create_new_version(self.route2, user_id)
        update_feed_document_create(self.route2, user_id)
        create_new_version(self.route3, user_id)
        update_feed_document_create(self.route3, user_id)

        self._add_association(session, user_ids, self.waypoint1, self.route3)
        self._add_association(session, user_ids, self.waypoint2, self.route3)
        self._add_association(session, user_ids, self.waypoint3, self.route3)
        self._add_tag(session, user_ids, self.route3)
        session.flush()

        outing1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing1_geometry,
            locales=[
                OutingLocale(
                    lang='en',
                    title='...',
                    description='...',
                    weather='sunny',
                    document_topic=DocumentTopic(topic_id=6),
                )
            ],
        )
        session.add(self.outing1)
        session.flush()

        create_new_version(self.outing1, user_id)
        update_feed_document_create(self.outing1, user_id)
        self._add_association(session, user_ids, self.route1, self.outing1)
        session.flush()

        outing1b_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.outing1b = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing1b_geometry,
            redirects_to=self.outing1.document_id,
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        session.add(self.outing1b)
        session.flush()

        create_new_version(self.outing1b, user_id)
        session.flush()

        outing2_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.outing2 = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            geometry=outing2_geometry,
            locales=[
                OutingLocale(
                    lang='en',
                    title='...',
                    description='...',
                    weather='sunny',
                    document_topic=DocumentTopic(topic_id=7),
                )
            ],
        )
        session.add(self.outing2)
        session.flush()

        create_new_version(self.outing2, user_id)
        update_feed_document_create(self.outing2, user_id)
        self._add_association(session, user_ids, self.route2, self.outing2)
        self._add_association(session, user_ids, self.route3, self.outing2)
        session.flush()

        self.article1 = Article(
            activities=['skitouring'],
            categories=['gear'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    lang='en',
                    title='Some article',
                    description='Some content',
                    document_topic=DocumentTopic(topic_id=8),
                )
            ],
        )
        session.add(self.article1)
        session.flush()

        create_new_version(self.article1, user_id)
        update_feed_document_create(self.article1, user_id)
        session.flush()

        self.article1.locales[0].title = 'Some other article title'
        article1_lang = self.article1.locales[0].lang
        session.flush()
        update_version(
            self.article1, user_id, 'new title', [UpdateType.LANG], [article1_lang]
        )
        session.flush()

        self._add_association(session, user_ids, self.route2, self.article1)
        self._add_association(session, user_ids, self.outing2, self.article1)
        session.flush()

        self.article2 = Article(
            activities=['skitouring'],
            categories=['gear'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    lang='en', title='Some other article', description='Some content'
                )
            ],
        )
        session.add(self.article2)
        session.flush()

        # Make the article older than 24h old
        written_at = datetime.datetime(2016, 1, 1, 0, 0, 0)
        create_new_version(self.article2, user_id, written_at)
        update_feed_document_create(self.article2, user_id)
        session.flush()

        self.book1 = Book(
            activities=['skitouring'],
            book_types=['biography'],
            locales=[
                DocumentLocale(
                    lang='en',
                    title='Some book',
                    description='Some content',
                    document_topic=DocumentTopic(topic_id=9),
                )
            ],
        )
        session.add(self.book1)
        session.flush()

        create_new_version(self.book1, user_id)
        update_feed_document_create(self.book1, user_id)
        self._add_association(session, user_ids, self.book1, self.route2)
        self._add_association(session, user_ids, self.book1, self.route3)
        session.flush()

        self.xreport1 = Xreport(
            event_activity='alpine_climbing',
            event_type='stone_ice_fall',
            locales=[
                XreportLocale(
                    lang='en',
                    title="Lac d'Annecy",
                    place='some place descrip. in english',
                    document_topic=DocumentTopic(topic_id=10),
                ),
                XreportLocale(
                    lang='fr',
                    title="Lac d'Annecy",
                    place='some place descrip. in french',
                    document_topic=DocumentTopic(topic_id=11),
                ),
            ],
        )
        session.add(self.xreport1)
        session.flush()

        create_new_version(self.xreport1, user_id)
        update_feed_document_create(self.xreport1, user_id)
        self._add_association(session, user_ids, self.outing2, self.xreport1)
        self._add_association(session, user_ids, self.route3, self.xreport1)
        session.flush()

        self.image1 = Image(
            filename='image1.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en',
                    title='Mont Blanc from the air',
                    description='...',
                    document_topic=DocumentTopic(topic_id=12),
                )
            ],
        )
        session.add(self.image1)
        session.flush()

        create_new_version(self.image1, user_id)
        self._add_association(session, user_ids, self.outing1, self.image1)
        self._add_association(session, user_ids, self.route3, self.image1)
        self._add_association(session, user_ids, self.waypoint3, self.image1)
        session.flush()

        update_feed_images_upload(
            [self.image1],
            [
                {
                    'filename': 'image1.jpg',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [{'lang': 'en', 'title': 'Mont Blanc from the air'}],
                    'associations': {
                        'outings': [{'document_id': self.outing1.document_id}],
                        'routes': [{'document_id': self.route3.document_id}],
                        'waypoints': [{'document_id': self.waypoint3.document_id}],
                    },
                }
            ],
            user_id,
        )

        self.image1.filename = 'image1.1.jpg'
        session.flush()
        update_version(
            self.image1, user_id, 'changed filename', [UpdateType.FIGURES], []
        )
        session.flush()

        self.topo_map1 = TopoMap(
            code='3232ET',
            editor='IGN',
            scale='25000',
            locales=[DocumentLocale(lang='fr', title='Belley')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
            ),
        )
        session.add(self.topo_map1)
        session.flush()
        session.add(
            TopoMapAssociation(document=self.waypoint2, topo_map=self.topo_map1)
        )
        session.add(
            TopoMapAssociation(document=self.waypoint3, topo_map=self.topo_map1)
        )
        session.add(TopoMapAssociation(document=self.route2, topo_map=self.topo_map1))
        session.add(TopoMapAssociation(document=self.route3, topo_map=self.topo_map1))
        session.flush()

        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            ),
        )
        session.add(self.area1)
        session.flush()
        session.add(AreaAssociation(document=self.waypoint2, area=self.area1))
        session.add(AreaAssociation(document=self.waypoint3, area=self.area1))
        session.add(AreaAssociation(document=self.route2, area=self.area1))
        session.add(AreaAssociation(document=self.route3, area=self.area1))
        session.flush()

    def _add_association(self, session, user_ids, parent_document, child_document):
        association = Association.create(
            parent_document=parent_document, child_document=child_document
        )
        session.add(association)
        session.add(association.get_log(user_ids['contributor']))

    def _add_tag(self, session, user_ids, document):
        document_id = document.document_id
        document_type = document.type
        user_id = user_ids['contributor']
        tag = DocumentTag(
            document_id=document_id, document_type=document_type, user_id=user_id
        )
        session.add(tag)
        log = DocumentTagLog(
            document_id=document_id,
            document_type=document_type,
            user_id=user_id,
            is_creation=True,
        )
        session.add(log)

    def _delete(self, client, document_id, expected_status):
        headers = auth_headers(username='moderator')
        return client.delete_json(
            self._prefix + str(document_id), headers=headers, status=expected_status
        )

    def test_non_unauthorized(self, client):
        client.delete_json(
            self._prefix + str(self.waypoint1.document_id), {}, status=403
        )

    def test_delete_non_existing_document(self, client):
        self._delete(client, 9999999, 404)

    def test_delete_main_waypoint(self, client):
        """Test that a main waypoint cannot be deleted."""
        response = self._delete(client, self.waypoint1.document_id, 400)
        assert_errors_contain(
            response.json,
            'document_id',
            'This waypoint cannot be deleted because it is a main waypoint.',
        )

    def test_delete_former_main_waypoint(self, client, session, user_ids):
        """Test that a former main waypoint can be deleted."""
        self.route3.main_waypoint_id = self.waypoint3.document_id
        session.flush()
        update_version(
            self.route3,
            user_ids['contributor'],
            'Update',
            [UpdateType.FIGURES],
            [],
        )

        self.route3.main_waypoint_id = self.waypoint1.document_id
        session.flush()
        update_version(
            self.route3,
            user_ids['contributor'],
            'Update',
            [UpdateType.FIGURES],
            [],
        )

        self._delete(client, self.waypoint3.document_id, 200)

    def test_delete_only_waypoint_of_route(self, client):
        """Test that the only waypoint of a route cannot be deleted."""
        response = self._delete(client, self.waypoint2.document_id, 400)
        assert_errors_contain(
            response.json,
            'document_id',
            'This waypoint cannot be deleted because '
            'it is the only waypoint associated to some routes.',
        )

    def test_delete_only_route_of_outing(self, client):
        """Test that a route cannot be deleted if it is the only route
        of some outing."""
        response = self._delete(client, self.route1.document_id, 400)
        assert_errors_contain(
            response.json,
            'document_id',
            'This route cannot be deleted because '
            'it is the only route associated to some outings.',
        )

    def _test_delete(
        self,
        client,
        session,
        document_id,
        clazz,
        clazz_locale,
        archive_clazz,
        archive_clazz_locale,
        expected_deleted_docs_count=1,
    ):

        # Get the number of documents before deleting
        initial_count = session.query(clazz).count()
        initial_doc_count = session.query(Document).count()

        self._delete(client, document_id, 200)

        # Check that only one document has been deleted
        count = session.query(clazz).count()
        assert initial_count - count == expected_deleted_docs_count
        count = session.query(Document).count()
        assert initial_doc_count - count == expected_deleted_docs_count

        # Check that the document versions table is cleared
        count = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .count()
        )
        assert 0 == count

        # Check that entries have been removed in the main tables
        count = session.query(clazz).filter(clazz.document_id == document_id).count()
        assert 0 == count
        count = (
            session.query(Document).filter(Document.document_id == document_id).count()
        )
        assert 0 == count
        if clazz_locale:
            count = (
                session.query(clazz_locale)
                .filter(clazz_locale.document_id == document_id)
                .count()
            )
            assert 0 == count
        count = (
            session.query(DocumentLocale)
            .filter(DocumentLocale.document_id == document_id)
            .count()
        )
        assert 0 == count
        count = (
            session.query(DocumentGeometry)
            .filter(DocumentGeometry.document_id == document_id)
            .count()
        )
        assert 0 == count

        # Check the archives have been cleared too
        count = (
            session.query(archive_clazz)
            .filter(archive_clazz.document_id == document_id)
            .count()
        )
        assert 0 == count
        count = (
            session.query(ArchiveDocument)
            .filter(ArchiveDocument.document_id == document_id)
            .count()
        )
        assert 0 == count
        if archive_clazz_locale:
            count = (
                session.query(archive_clazz_locale)
                .filter(archive_clazz_locale.document_id == document_id)
                .count()
            )
            assert 0 == count
        count = (
            session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == document_id)
            .count()
        )
        assert 0 == count
        count = (
            session.query(ArchiveDocumentGeometry)
            .filter(ArchiveDocumentGeometry.document_id == document_id)
            .count()
        )
        assert 0 == count

        # check associations have been cleared
        association_count = (
            session.query(Association)
            .filter(
                or_(
                    Association.parent_document_id == document_id,
                    Association.child_document_id == document_id,
                )
            )
            .count()
        )
        assert 0 == association_count
        association_log_count = (
            session.query(AssociationLog)
            .filter(
                or_(
                    AssociationLog.parent_document_id == document_id,
                    AssociationLog.child_document_id == document_id,
                )
            )
            .count()
        )
        assert 0 == association_log_count
        association_count = (
            session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.document_id == document_id)
            .count()
        )
        assert 0 == association_count
        association_count = (
            session.query(AreaAssociation)
            .filter(AreaAssociation.document_id == document_id)
            .count()
        )
        assert 0 == association_count

        # Check the feed has been cleared
        feed_count = (
            session.query(DocumentChange)
            .filter(DocumentChange.document_id == document_id)
            .count()
        )
        assert 0 == feed_count

    def test_delete_waypoint(self, client, session):
        self._test_delete(
            client,
            session,
            self.waypoint3.document_id,
            Waypoint,
            WaypointLocale,
            ArchiveWaypoint,
            ArchiveWaypointLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route3.document_id, 2)
        scenarios.check_cache_version(session, self.image1.document_id, 2)

    def test_delete_route(self, client, session):
        self._test_delete(
            client,
            session,
            self.route3.document_id,
            Route,
            RouteLocale,
            ArchiveRoute,
            ArchiveRouteLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.waypoint1.document_id, 3)
        scenarios.check_cache_version(session, self.waypoint2.document_id, 3)
        scenarios.check_cache_version(session, self.waypoint3.document_id, 3)
        scenarios.check_cache_version(session, self.outing2.document_id, 2)
        scenarios.check_cache_version(session, self.book1.document_id, 2)
        scenarios.check_cache_version(session, self.xreport1.document_id, 2)
        scenarios.check_cache_version(session, self.image1.document_id, 2)

    def _count_tags(self, session, document_id):
        nb_tags = (
            session.query(DocumentTag)
            .filter(DocumentTag.document_id == document_id)
            .count()
        )
        nb_logs = (
            session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == document_id)
            .count()
        )
        return nb_tags, nb_logs

    def test_delete_route_with_tags(self, client, session):
        nb_tags, nb_logs = self._count_tags(session, self.route3.document_id)
        assert nb_tags == 1
        assert nb_logs == 1

        self._test_delete(
            client,
            session,
            self.route3.document_id,
            Route,
            RouteLocale,
            ArchiveRoute,
            ArchiveRouteLocale,
        )

        # Check related tags have been removed
        nb_tags, nb_logs = self._count_tags(session, self.route3.document_id)
        assert nb_tags == 0
        assert nb_logs == 0

    def test_delete_outing(self, client, session):
        # outing1b redirects to outing1 => 2 documents to delete
        self._test_delete(
            client,
            session,
            self.outing1.document_id,
            Outing,
            OutingLocale,
            ArchiveOuting,
            ArchiveOutingLocale,
            2,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route1.document_id, 2)
        scenarios.check_cache_version(session, self.image1.document_id, 2)

    def test_delete_outing_route_waypoint(self, client, session):
        self._test_delete(
            client,
            session,
            self.outing2.document_id,
            Outing,
            OutingLocale,
            ArchiveOuting,
            ArchiveOutingLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route2.document_id, 2)
        scenarios.check_cache_version(session, self.route3.document_id, 2)
        scenarios.check_cache_version(session, self.article1.document_id, 2)
        scenarios.check_cache_version(session, self.xreport1.document_id, 2)

        self._test_delete(
            client,
            session,
            self.route2.document_id,
            Route,
            RouteLocale,
            ArchiveRoute,
            ArchiveRouteLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.waypoint2.document_id, 4)
        scenarios.check_cache_version(session, self.article1.document_id, 3)
        scenarios.check_cache_version(session, self.book1.document_id, 2)

        self._test_delete(
            client,
            session,
            self.waypoint2.document_id,
            Waypoint,
            WaypointLocale,
            ArchiveWaypoint,
            ArchiveWaypointLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route3.document_id, 3)

    def test_delete_article(self, client, session):
        self._test_delete(
            client,
            session,
            self.article1.document_id,
            Article,
            None,
            ArchiveArticle,
            None,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route2.document_id, 2)
        scenarios.check_cache_version(session, self.outing2.document_id, 2)

    def test_delete_book(self, client, session):
        self._test_delete(
            client, session, self.book1.document_id, Book, None, ArchiveBook, None
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route2.document_id, 2)
        scenarios.check_cache_version(session, self.route3.document_id, 2)

    def test_delete_xreport(self, client, session):
        self._test_delete(
            client,
            session,
            self.xreport1.document_id,
            Xreport,
            XreportLocale,
            ArchiveXreport,
            ArchiveXreportLocale,
        )

        # Check that associated documents cache versions have been incremented
        scenarios.check_cache_version(session, self.route3.document_id, 2)
        scenarios.check_cache_version(session, self.outing2.document_id, 2)

    def test_delete_image(self, client, session, settings):
        call = {'times': 0}

        @all_requests
        def image_service_mock(url, request):
            call['times'] += 1
            call['request.body'] = request.body.split('&')
            call['request.url'] = request.url
            return {'status_code': 200, 'content': ''}

        with HTTMock(image_service_mock):
            self._test_delete(
                client,
                session,
                self.image1.document_id,
                Image,
                None,
                ArchiveImage,
                None,
            )
            assert call['times'] == 1
            assert 'filenames=image1.1.jpg' in call['request.body']
            assert 'filenames=image1.jpg' in call['request.body']
            assert call['request.url'] == settings['image_backend.url'] + '/delete'
            scenarios.check_cache_version(session, self.waypoint3.document_id, 2)
            scenarios.check_cache_version(session, self.route3.document_id, 2)
            scenarios.check_cache_version(session, self.outing1.document_id, 2)

    def test_delete_image_error_deleting_files(self, client, session, settings):
        """Test that the delete request is also successful if the image files
        cannot be deleted.
        """
        call = {'times': 0}

        @all_requests
        def image_service_mock(url, request):
            call['times'] += 1
            call['request.body'] = request.body.split('&')
            call['request.url'] = request.url
            return {'status_code': 500, 'content': ''}

        with HTTMock(image_service_mock):
            self._test_delete(
                client,
                session,
                self.image1.document_id,
                Image,
                None,
                ArchiveImage,
                None,
            )
            assert call['times'] == 1
            assert 'filenames=image1.1.jpg' in call['request.body']
            assert 'filenames=image1.jpg' in call['request.body']
            assert call['request.url'] == settings['image_backend.url'] + '/delete'
            scenarios.check_cache_version(session, self.waypoint3.document_id, 2)
            scenarios.check_cache_version(session, self.route3.document_id, 2)
            scenarios.check_cache_version(session, self.outing1.document_id, 2)

    def test_delete_collaborative_doc(self, client):
        # Collaborative documents cannot be deleted, even by their authors:
        headers = auth_headers(username='contributor')
        client.delete_json(
            self._prefix + str(self.waypoint4.document_id),
            {},
            headers=headers,
            status=400,
        )

        # Moderators can:
        headers = auth_headers(username='moderator')
        client.delete_json(
            self._prefix + str(self.waypoint4.document_id),
            {},
            headers=headers,
            status=200,
        )

    def test_delete_personal_doc_not_author(self, client):
        # Personal documents cannot be deleted by anyone:
        headers = auth_headers(username='contributor2')
        client.delete_json(
            self._prefix + str(self.article1.document_id),
            {},
            headers=headers,
            status=400,
        )

        # Except by moderators:
        headers = auth_headers(username='moderator')
        client.delete_json(
            self._prefix + str(self.article1.document_id),
            {},
            headers=headers,
            status=200,
        )

    def test_delete_personal_doc_author_less_24h(self, client):
        # article1 has just been created by 'contributor'
        headers = auth_headers(username='contributor')
        client.delete_json(
            self._prefix + str(self.article1.document_id),
            {},
            headers=headers,
            status=200,
        )

    def test_delete_personal_doc_author_more_24h(self, client):
        # article2 is older than 24h
        headers = auth_headers(username='contributor')
        client.delete_json(
            self._prefix + str(self.article2.document_id),
            {},
            headers=headers,
            status=400,
        )

    def test_delete_locale_non_unauthorized(self, client):
        client.delete_json(
            self._prefix + str(self.waypoint1.document_id) + '/fr', {}, status=403
        )

        headers = auth_headers(username='contributor')
        client.delete_json(
            self._prefix + str(self.waypoint1.document_id) + '/fr',
            {},
            headers=headers,
            status=403,
        )

    def _delete_locale(self, client, document_id, lang, expected_status):
        headers = auth_headers(username='moderator')
        return client.delete_json(
            self._prefix + str(document_id) + '/' + lang,
            headers=headers,
            status=expected_status,
        )

    def test_delete_locale_non_existing_document(self, client):
        self._delete_locale(client, 9999999, 'fr', 404)

    def test_delete_locale_non_existing_locale(self, client):
        self._delete_locale(client, self.waypoint1.document_id, 'de', 400)

    def test_delete_locale_main_waypoint_with_only_one_locale(self, client):
        response = self._delete_locale(client, self.waypoint1.document_id, 'fr', 400)
        assert_errors_contain(
            response.json,
            'document_id',
            'This waypoint cannot be deleted because it is a main waypoint.',
        )

    def _test_delete_locale(self, client, session, document_id, lang):
        available_langs = get_available_langs(document_id)

        initial_other_locale_archives_count = (
            session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == document_id)
            .filter(ArchiveDocumentLocale.lang != lang)
            .count()
        )

        initial_other_locale_versions_count = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang != lang)
            .count()
        )

        self._delete_locale(client, document_id, lang, 200)

        # Check that deleted locale is no longer available
        available_langs.remove(lang)
        final_available_langs = get_available_langs(document_id)
        # if the document had only one locale, it is deleted and
        # get_available_langs() returns None
        assert (not final_available_langs) == (not available_langs)
        if available_langs:
            assert Counter(final_available_langs) == Counter(available_langs)

        # Check that archives have been removed too
        count = (
            session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == document_id)
            .filter(ArchiveDocumentLocale.lang == lang)
            .count()
        )
        assert 0 == count

        # but not other locale archives
        other_locale_archives_count = (
            session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == document_id)
            .filter(ArchiveDocumentLocale.lang != lang)
            .count()
        )
        assert other_locale_archives_count == initial_other_locale_archives_count

        # Check that the document versions table is cleared
        count = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang == lang)
            .count()
        )
        assert 0 == count

        # but not for other locales
        other_locale_versions_count = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang != lang)
            .count()
        )
        assert other_locale_versions_count == initial_other_locale_versions_count

        # Check the feed has been updated
        feed_items_langs = (
            session.query(DocumentChange.langs)
            .filter(DocumentChange.document_id == document_id)
            .all()
        )
        for langs in feed_items_langs:
            assert lang not in langs

    def test_delete_locale_waypoint(self, client, session):
        self._test_delete_locale(client, session, self.waypoint3.document_id, 'fr')

    def test_delete_locale_added_in_its_own_version(self, client, session, user_ids):
        # a translation added later has a history metadata entry of its own,
        # which the deletion removes too
        self.waypoint3.locales.append(
            WaypointLocale(lang='de', title='Granier', description='...')
        )
        session.flush()
        update_version(
            self.waypoint3,
            user_ids['contributor'],
            'add de',
            [UpdateType.LANG],
            ['de'],
        )
        history_metadata_id = (
            session.query(DocumentVersion.history_metadata_id)
            .filter(DocumentVersion.document_id == self.waypoint3.document_id)
            .filter(DocumentVersion.lang == 'de')
            .scalar()
        )

        self._test_delete_locale(client, session, self.waypoint3.document_id, 'de')

        assert session.get(HistoryMetaData, history_metadata_id) is None

    def test_delete_locale_route_with_only_one_locale(self, client, session):
        document_id = self.route3.document_id
        self._test_delete_locale(client, session, document_id, 'en')

        # Test that the document has fully been deleted
        count = (
            session.query(Document).filter(Document.document_id == document_id).count()
        )
        assert count == 0
        count = (
            session.query(ArchiveDocument)
            .filter(ArchiveDocument.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(DocumentLocale)
            .filter(DocumentLocale.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(DocumentGeometry)
            .filter(DocumentGeometry.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(ArchiveDocumentGeometry)
            .filter(ArchiveDocumentGeometry.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .count()
        )
        assert count == 0
        count = (
            session.query(Association)
            .filter(
                or_(
                    Association.parent_document_id == document_id,
                    Association.child_document_id == document_id,
                )
            )
            .count()
        )
        assert count == 0
