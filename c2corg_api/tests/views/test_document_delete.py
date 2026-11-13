import datetime
from collections import Counter
from dataclasses import dataclass

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

PREFIX = '/documents/delete/'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    waypoint4: Waypoint
    route1: Route
    route2: Route
    route3: Route
    outing1: Outing
    outing1b: Outing
    outing2: Outing
    article1: Article
    article2: Article
    book1: Book
    xreport1: Xreport
    image1: Image
    topo_map1: TopoMap
    area1: Area


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    user_id = user_ids['contributor']

    waypoint1 = Waypoint(
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
    session.add(waypoint1)

    waypoint2 = Waypoint(
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
    session.add(waypoint2)

    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=3,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    waypoint3.locales.append(
        WaypointLocale(
            lang='en',
            title='Mont Granier',
            description='...',
            access='yep',
            document_topic=DocumentTopic(topic_id=2),
        )
    )
    waypoint3.locales.append(
        WaypointLocale(
            lang='fr',
            title='Mont Granier',
            description='...',
            access='ouai',
            document_topic=DocumentTopic(topic_id=3),
        )
    )
    session.add(waypoint3)
    session.flush()

    waypoint4 = Waypoint(
        waypoint_type='summit',
        elevation=3,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    waypoint4.locales.append(
        WaypointLocale(lang='en', title='Mont Ventoux', description='...')
    )
    session.add(waypoint4)
    session.flush()

    create_new_version(waypoint1, user_id)
    update_feed_document_create(waypoint1, user_id)
    create_new_version(waypoint2, user_id)
    update_feed_document_create(waypoint2, user_id)
    create_new_version(waypoint3, user_id)
    update_feed_document_create(waypoint3, user_id)
    create_new_version(waypoint4, user_id)
    update_feed_document_create(waypoint4, user_id)
    session.flush()

    route1_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    route1 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        main_waypoint_id=waypoint1.document_id,
        geometry=route1_geometry,
    )
    route1.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
        )
    )
    session.add(route1)

    route2_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    route2 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        geometry=route2_geometry,
    )
    route2.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
            document_topic=DocumentTopic(topic_id=4),
        )
    )
    session.add(route2)
    session.flush()

    _add_association(session, user_ids, waypoint1, route1)
    _add_association(session, user_ids, waypoint2, route2)
    session.flush()

    route3_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    route3 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        geometry=route3_geometry,
    )
    route3.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
            document_topic=DocumentTopic(topic_id=5),
        )
    )
    session.add(route3)
    session.flush()

    create_new_version(route1, user_id)
    update_feed_document_create(route1, user_id)
    create_new_version(route2, user_id)
    update_feed_document_create(route2, user_id)
    create_new_version(route3, user_id)
    update_feed_document_create(route3, user_id)

    _add_association(session, user_ids, waypoint1, route3)
    _add_association(session, user_ids, waypoint2, route3)
    _add_association(session, user_ids, waypoint3, route3)
    _add_tag(session, user_ids, route3)
    session.flush()

    outing1_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    outing1 = Outing(
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
    session.add(outing1)
    session.flush()

    create_new_version(outing1, user_id)
    update_feed_document_create(outing1, user_id)
    _add_association(session, user_ids, route1, outing1)
    session.flush()

    outing1b_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    outing1b = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        geometry=outing1b_geometry,
        redirects_to=outing1.document_id,
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )
    session.add(outing1b)
    session.flush()

    create_new_version(outing1b, user_id)
    session.flush()

    outing2_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    outing2 = Outing(
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
    session.add(outing2)
    session.flush()

    create_new_version(outing2, user_id)
    update_feed_document_create(outing2, user_id)
    _add_association(session, user_ids, route2, outing2)
    _add_association(session, user_ids, route3, outing2)
    session.flush()

    article1 = Article(
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
    session.add(article1)
    session.flush()

    create_new_version(article1, user_id)
    update_feed_document_create(article1, user_id)
    session.flush()

    article1.locales[0].title = 'Some other article title'
    article1_lang = article1.locales[0].lang
    session.flush()
    update_version(article1, user_id, 'new title', [UpdateType.LANG], [article1_lang])
    session.flush()

    _add_association(session, user_ids, route2, article1)
    _add_association(session, user_ids, outing2, article1)
    session.flush()

    article2 = Article(
        activities=['skitouring'],
        categories=['gear'],
        article_type='personal',
        locales=[
            DocumentLocale(
                lang='en', title='Some other article', description='Some content'
            )
        ],
    )
    session.add(article2)
    session.flush()

    # Make the article older than 24h old
    written_at = datetime.datetime(2016, 1, 1, 0, 0, 0)
    create_new_version(article2, user_id, written_at)
    update_feed_document_create(article2, user_id)
    session.flush()

    book1 = Book(
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
    session.add(book1)
    session.flush()

    create_new_version(book1, user_id)
    update_feed_document_create(book1, user_id)
    _add_association(session, user_ids, book1, route2)
    _add_association(session, user_ids, book1, route3)
    session.flush()

    xreport1 = Xreport(
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
    session.add(xreport1)
    session.flush()

    create_new_version(xreport1, user_id)
    update_feed_document_create(xreport1, user_id)
    _add_association(session, user_ids, outing2, xreport1)
    _add_association(session, user_ids, route3, xreport1)
    session.flush()

    image1 = Image(
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
    session.add(image1)
    session.flush()

    create_new_version(image1, user_id)
    _add_association(session, user_ids, outing1, image1)
    _add_association(session, user_ids, route3, image1)
    _add_association(session, user_ids, waypoint3, image1)
    session.flush()

    update_feed_images_upload(
        [image1],
        [
            {
                'filename': 'image1.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [{'lang': 'en', 'title': 'Mont Blanc from the air'}],
                'associations': {
                    'outings': [{'document_id': outing1.document_id}],
                    'routes': [{'document_id': route3.document_id}],
                    'waypoints': [{'document_id': waypoint3.document_id}],
                },
            }
        ],
        user_id,
    )

    image1.filename = 'image1.1.jpg'
    session.flush()
    update_version(image1, user_id, 'changed filename', [UpdateType.FIGURES], [])
    session.flush()

    topo_map1 = TopoMap(
        code='3232ET',
        editor='IGN',
        scale='25000',
        locales=[DocumentLocale(lang='fr', title='Belley')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
        ),
    )
    session.add(topo_map1)
    session.flush()
    session.add(TopoMapAssociation(document=waypoint2, topo_map=topo_map1))
    session.add(TopoMapAssociation(document=waypoint3, topo_map=topo_map1))
    session.add(TopoMapAssociation(document=route2, topo_map=topo_map1))
    session.add(TopoMapAssociation(document=route3, topo_map=topo_map1))
    session.flush()

    area1 = Area(
        area_type='range',
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
        ),
    )
    session.add(area1)
    session.flush()
    session.add(AreaAssociation(document=waypoint2, area=area1))
    session.add(AreaAssociation(document=waypoint3, area=area1))
    session.add(AreaAssociation(document=route2, area=area1))
    session.add(AreaAssociation(document=route3, area=area1))
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        waypoint4=waypoint4,
        route1=route1,
        route2=route2,
        route3=route3,
        outing1=outing1,
        outing1b=outing1b,
        outing2=outing2,
        article1=article1,
        article2=article2,
        book1=book1,
        xreport1=xreport1,
        image1=image1,
        topo_map1=topo_map1,
        area1=area1,
    )


def _add_association(session, user_ids, parent_document, child_document):
    association = Association.create(
        parent_document=parent_document, child_document=child_document
    )
    session.add(association)
    session.add(association.get_log(user_ids['contributor']))


def _add_tag(session, user_ids, document):
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


def _delete(client, document_id, expected_status):
    headers = auth_headers(username='moderator')
    return client.delete_json(
        PREFIX + str(document_id), headers=headers, status=expected_status
    )


def test_non_unauthorized(client, docs):
    client.delete_json(PREFIX + str(docs.waypoint1.document_id), {}, status=403)


def test_delete_non_existing_document(client):
    _delete(client, 9999999, 404)


def test_delete_main_waypoint(client, docs):
    """Test that a main waypoint cannot be deleted."""
    response = _delete(client, docs.waypoint1.document_id, 400)
    assert_errors_contain(
        response.json,
        'document_id',
        'This waypoint cannot be deleted because it is a main waypoint.',
    )


def test_delete_former_main_waypoint(client, session, user_ids, docs):
    """Test that a former main waypoint can be deleted."""
    docs.route3.main_waypoint_id = docs.waypoint3.document_id
    session.flush()
    update_version(
        docs.route3,
        user_ids['contributor'],
        'Update',
        [UpdateType.FIGURES],
        [],
    )

    docs.route3.main_waypoint_id = docs.waypoint1.document_id
    session.flush()
    update_version(
        docs.route3,
        user_ids['contributor'],
        'Update',
        [UpdateType.FIGURES],
        [],
    )

    _delete(client, docs.waypoint3.document_id, 200)


def test_delete_only_waypoint_of_route(client, docs):
    """Test that the only waypoint of a route cannot be deleted."""
    response = _delete(client, docs.waypoint2.document_id, 400)
    assert_errors_contain(
        response.json,
        'document_id',
        'This waypoint cannot be deleted because '
        'it is the only waypoint associated to some routes.',
    )


def test_delete_only_route_of_outing(client, docs):
    """Test that a route cannot be deleted if it is the only route
    of some outing."""
    response = _delete(client, docs.route1.document_id, 400)
    assert_errors_contain(
        response.json,
        'document_id',
        'This route cannot be deleted because '
        'it is the only route associated to some outings.',
    )


def _test_delete(
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

    _delete(client, document_id, 200)

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
    count = session.query(Document).filter(Document.document_id == document_id).count()
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


def test_delete_waypoint(client, session, docs):
    _test_delete(
        client,
        session,
        docs.waypoint3.document_id,
        Waypoint,
        WaypointLocale,
        ArchiveWaypoint,
        ArchiveWaypointLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route3.document_id, 2)
    scenarios.check_cache_version(session, docs.image1.document_id, 2)


def test_delete_route(client, session, docs):
    _test_delete(
        client,
        session,
        docs.route3.document_id,
        Route,
        RouteLocale,
        ArchiveRoute,
        ArchiveRouteLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 3)
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 3)
    scenarios.check_cache_version(session, docs.waypoint3.document_id, 3)
    scenarios.check_cache_version(session, docs.outing2.document_id, 2)
    scenarios.check_cache_version(session, docs.book1.document_id, 2)
    scenarios.check_cache_version(session, docs.xreport1.document_id, 2)
    scenarios.check_cache_version(session, docs.image1.document_id, 2)


def _count_tags(session, document_id):
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


def test_delete_route_with_tags(client, session, docs):
    nb_tags, nb_logs = _count_tags(session, docs.route3.document_id)
    assert nb_tags == 1
    assert nb_logs == 1

    _test_delete(
        client,
        session,
        docs.route3.document_id,
        Route,
        RouteLocale,
        ArchiveRoute,
        ArchiveRouteLocale,
    )

    # Check related tags have been removed
    nb_tags, nb_logs = _count_tags(session, docs.route3.document_id)
    assert nb_tags == 0
    assert nb_logs == 0


def test_delete_outing(client, session, docs):
    # outing1b redirects to outing1 => 2 documents to delete
    _test_delete(
        client,
        session,
        docs.outing1.document_id,
        Outing,
        OutingLocale,
        ArchiveOuting,
        ArchiveOutingLocale,
        2,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route1.document_id, 2)
    scenarios.check_cache_version(session, docs.image1.document_id, 2)


def test_delete_outing_route_waypoint(client, session, docs):
    _test_delete(
        client,
        session,
        docs.outing2.document_id,
        Outing,
        OutingLocale,
        ArchiveOuting,
        ArchiveOutingLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route2.document_id, 2)
    scenarios.check_cache_version(session, docs.route3.document_id, 2)
    scenarios.check_cache_version(session, docs.article1.document_id, 2)
    scenarios.check_cache_version(session, docs.xreport1.document_id, 2)

    _test_delete(
        client,
        session,
        docs.route2.document_id,
        Route,
        RouteLocale,
        ArchiveRoute,
        ArchiveRouteLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 4)
    scenarios.check_cache_version(session, docs.article1.document_id, 3)
    scenarios.check_cache_version(session, docs.book1.document_id, 2)

    _test_delete(
        client,
        session,
        docs.waypoint2.document_id,
        Waypoint,
        WaypointLocale,
        ArchiveWaypoint,
        ArchiveWaypointLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route3.document_id, 3)


def test_delete_article(client, session, docs):
    _test_delete(
        client,
        session,
        docs.article1.document_id,
        Article,
        None,
        ArchiveArticle,
        None,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route2.document_id, 2)
    scenarios.check_cache_version(session, docs.outing2.document_id, 2)


def test_delete_with_history_metadata_shared_with_another_document(
    client, session, docs
):
    # documents changed in one changeset (as the migration from v5 did) share a
    # history metadata entry: kept for the other document
    shared_id = (
        session.query(DocumentVersion.history_metadata_id)
        .filter(DocumentVersion.document_id == docs.route2.document_id)
        .limit(1)
        .scalar()
    )
    session.query(DocumentVersion).filter(
        DocumentVersion.document_id == docs.article1.document_id
    ).update({DocumentVersion.history_metadata_id: shared_id})
    session.flush()

    _test_delete(
        client,
        session,
        docs.article1.document_id,
        Article,
        None,
        ArchiveArticle,
        None,
    )

    assert session.get(HistoryMetaData, shared_id) is not None


def test_delete_book(client, session, docs):
    _test_delete(client, session, docs.book1.document_id, Book, None, ArchiveBook, None)

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route2.document_id, 2)
    scenarios.check_cache_version(session, docs.route3.document_id, 2)


def test_delete_xreport(client, session, docs):
    _test_delete(
        client,
        session,
        docs.xreport1.document_id,
        Xreport,
        XreportLocale,
        ArchiveXreport,
        ArchiveXreportLocale,
    )

    # Check that associated documents cache versions have been incremented
    scenarios.check_cache_version(session, docs.route3.document_id, 2)
    scenarios.check_cache_version(session, docs.outing2.document_id, 2)


def test_delete_image(client, session, settings, docs):
    call = {'times': 0}

    @all_requests
    def image_service_mock(url, request):
        call['times'] += 1
        call['request.body'] = request.body.split('&')
        call['request.url'] = request.url
        return {'status_code': 200, 'content': ''}

    with HTTMock(image_service_mock):
        _test_delete(
            client,
            session,
            docs.image1.document_id,
            Image,
            None,
            ArchiveImage,
            None,
        )
        assert call['times'] == 1
        assert 'filenames=image1.1.jpg' in call['request.body']
        assert 'filenames=image1.jpg' in call['request.body']
        assert call['request.url'] == settings['image_backend.url'] + '/delete'
        scenarios.check_cache_version(session, docs.waypoint3.document_id, 2)
        scenarios.check_cache_version(session, docs.route3.document_id, 2)
        scenarios.check_cache_version(session, docs.outing1.document_id, 2)


def test_delete_image_error_deleting_files(client, session, settings, docs):
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
        _test_delete(
            client,
            session,
            docs.image1.document_id,
            Image,
            None,
            ArchiveImage,
            None,
        )
        assert call['times'] == 1
        assert 'filenames=image1.1.jpg' in call['request.body']
        assert 'filenames=image1.jpg' in call['request.body']
        assert call['request.url'] == settings['image_backend.url'] + '/delete'
        scenarios.check_cache_version(session, docs.waypoint3.document_id, 2)
        scenarios.check_cache_version(session, docs.route3.document_id, 2)
        scenarios.check_cache_version(session, docs.outing1.document_id, 2)


def test_delete_collaborative_doc(client, docs):
    # Collaborative documents cannot be deleted, even by their authors:
    headers = auth_headers(username='contributor')
    client.delete_json(
        PREFIX + str(docs.waypoint4.document_id),
        {},
        headers=headers,
        status=400,
    )

    # Moderators can:
    headers = auth_headers(username='moderator')
    client.delete_json(
        PREFIX + str(docs.waypoint4.document_id),
        {},
        headers=headers,
        status=200,
    )


def test_delete_personal_doc_not_author(client, docs):
    # Personal documents cannot be deleted by anyone:
    headers = auth_headers(username='contributor2')
    client.delete_json(
        PREFIX + str(docs.article1.document_id),
        {},
        headers=headers,
        status=400,
    )

    # Except by moderators:
    headers = auth_headers(username='moderator')
    client.delete_json(
        PREFIX + str(docs.article1.document_id),
        {},
        headers=headers,
        status=200,
    )


def test_delete_personal_doc_author_less_24h(client, docs):
    # article1 has just been created by 'contributor'
    headers = auth_headers(username='contributor')
    client.delete_json(
        PREFIX + str(docs.article1.document_id),
        {},
        headers=headers,
        status=200,
    )


def test_delete_personal_doc_author_more_24h(client, docs):
    # article2 is older than 24h
    headers = auth_headers(username='contributor')
    client.delete_json(
        PREFIX + str(docs.article2.document_id),
        {},
        headers=headers,
        status=400,
    )


def test_delete_locale_non_unauthorized(client, docs):
    client.delete_json(PREFIX + str(docs.waypoint1.document_id) + '/fr', {}, status=403)

    headers = auth_headers(username='contributor')
    client.delete_json(
        PREFIX + str(docs.waypoint1.document_id) + '/fr',
        {},
        headers=headers,
        status=403,
    )


def _delete_locale(client, document_id, lang, expected_status):
    headers = auth_headers(username='moderator')
    return client.delete_json(
        PREFIX + str(document_id) + '/' + lang,
        headers=headers,
        status=expected_status,
    )


def test_delete_locale_non_existing_document(client):
    _delete_locale(client, 9999999, 'fr', 404)


def test_delete_locale_non_existing_locale(client, docs):
    _delete_locale(client, docs.waypoint1.document_id, 'de', 400)


def test_delete_locale_main_waypoint_with_only_one_locale(client, docs):
    response = _delete_locale(client, docs.waypoint1.document_id, 'fr', 400)
    assert_errors_contain(
        response.json,
        'document_id',
        'This waypoint cannot be deleted because it is a main waypoint.',
    )


def _test_delete_locale(client, session, document_id, lang):
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

    _delete_locale(client, document_id, lang, 200)

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


def test_delete_locale_waypoint(client, session, docs):
    _test_delete_locale(client, session, docs.waypoint3.document_id, 'fr')


def test_delete_locale_added_in_its_own_version(client, session, user_ids, docs):
    # a translation added later has a history metadata entry of its own,
    # which the deletion removes too
    docs.waypoint3.locales.append(
        WaypointLocale(lang='de', title='Granier', description='...')
    )
    session.flush()
    update_version(
        docs.waypoint3,
        user_ids['contributor'],
        'add de',
        [UpdateType.LANG],
        ['de'],
    )
    history_metadata_id = (
        session.query(DocumentVersion.history_metadata_id)
        .filter(DocumentVersion.document_id == docs.waypoint3.document_id)
        .filter(DocumentVersion.lang == 'de')
        .scalar()
    )

    _test_delete_locale(client, session, docs.waypoint3.document_id, 'de')

    assert session.get(HistoryMetaData, history_metadata_id) is None


def test_delete_locale_route_with_only_one_locale(client, session, docs):
    document_id = docs.route3.document_id
    _test_delete_locale(client, session, document_id, 'en')

    # Test that the document has fully been deleted
    count = session.query(Document).filter(Document.document_id == document_id).count()
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
