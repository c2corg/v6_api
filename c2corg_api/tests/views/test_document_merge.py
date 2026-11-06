from dataclasses import dataclass

import pytest
from httmock import HTTMock, all_requests
from sqlalchemy.sql.expression import or_

from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import DocumentGeometry, DocumentLocale, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import DocumentChange, update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.tests.views import scenarios
from c2corg_api.views.document import create_new_version, update_version

PREFIX = '/documents/merge'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    waypoint4: Waypoint
    route1: Route
    route2: Route
    image1: Image
    image2: Image


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor_id = user_ids['contributor']

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
                summary='The heighest point in Europe',
            )
        ],
    )
    session.add(waypoint2)
    session.flush()
    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=4985,
        redirects_to=waypoint1.document_id,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont Blanc',
                description='...',
                summary='The heighest point in Europe',
            )
        ],
    )
    session.add(waypoint3)
    waypoint4 = Waypoint(
        waypoint_type='summit',
        elevation=4985,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont Blanc',
                description='...',
                summary='The heighest point in Europe',
            )
        ],
    )
    session.add(waypoint4)
    session.flush()

    route1 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        main_waypoint_id=waypoint1.document_id,
        locales=[
            RouteLocale(
                lang='fr',
                title='Mont Blanc du ciel',
                description='...',
                summary='Ski',
            )
        ],
    )
    session.add(route1)

    route2 = Route(
        activities=['skitouring'],
        elevation_max=1400,
        elevation_min=700,
        main_waypoint_id=waypoint1.document_id,
        locales=[
            RouteLocale(
                lang='fr',
                title='Mont Blanc du soleil',
                description='...',
                summary='Ski',
            )
        ],
    )
    session.add(route2)
    session.flush()

    create_new_version(waypoint1, contributor_id)
    update_feed_document_create(waypoint1, contributor_id)

    create_new_version(route1, contributor_id)
    update_feed_document_create(route1, contributor_id)

    create_new_version(route2, contributor_id)
    update_feed_document_create(route2, contributor_id)

    association = Association.create(parent_document=waypoint1, child_document=route1)
    session.add(association)
    session.add(association.get_log(user_ids['contributor']))

    association = Association.create(parent_document=waypoint1, child_document=route2)
    session.add(association)
    session.add(association.get_log(user_ids['contributor']))

    association = Association.create(
        parent_document=waypoint1, child_document=waypoint4
    )
    session.add(association)
    session.add(association.get_log(user_ids['contributor']))

    association = Association.create(
        parent_document=waypoint2, child_document=waypoint4
    )
    session.add(association)
    session.add(association.get_log(user_ids['contributor']))
    session.flush()

    image1 = Image(
        filename='image1.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
        locales=[
            DocumentLocale(
                lang='en', title='Mont Blanc from the air', description='...'
            )
        ],
    )
    session.add(image1)

    image2 = Image(
        filename='image2.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
        locales=[
            DocumentLocale(
                lang='en', title='Mont Blanc from the air', description='...'
            )
        ],
    )
    session.add(image2)

    session.flush()
    create_new_version(image1, contributor_id)
    session.flush()

    image1.filename = 'image1.1.jpg'
    session.flush()
    update_version(image1, contributor_id, 'changed filename', [UpdateType.FIGURES], [])
    session.flush()

    session.add(
        DocumentTag(
            document_id=route1.document_id,
            document_type=ROUTE_TYPE,
            user_id=contributor_id,
        )
    )
    session.add(
        DocumentTagLog(
            document_id=route1.document_id,
            document_type=ROUTE_TYPE,
            user_id=contributor_id,
            is_creation=True,
        )
    )
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        waypoint4=waypoint4,
        route1=route1,
        route2=route2,
        image1=image1,
        image2=image2,
    )


def _post(client, body, expected_status):
    headers = auth_headers(username='moderator')
    return send_json(
        client, 'post', PREFIX, body, headers=headers, status=expected_status
    )


def test_non_unauthorized(client):
    send_json(client, 'post', PREFIX, {}, status=403)

    headers = auth_headers(username='contributor')
    send_json(client, 'post', PREFIX, {}, headers=headers, status=403)


def test_empty_body(client):
    _post(client, {}, 422)


def test_same_document(client, docs):
    _post(
        client,
        {
            'source_document_id': docs.waypoint1.document_id,
            'target_document_id': docs.waypoint1.document_id,
        },
        400,
    )


def test_non_existing_documents(client):
    _post(
        client,
        {'source_document_id': -9999999, 'target_document_id': -99999999},
        400,
    )


def test_not_same_types(client, docs):
    _post(
        client,
        {
            'source_document_id': docs.waypoint1.document_id,
            'target_document_id': docs.route1.document_id,
        },
        400,
    )


def test_already_merged(client, docs):
    _post(
        client,
        {
            'source_document_id': docs.waypoint3.document_id,
            'target_document_id': docs.waypoint2.document_id,
        },
        400,
    )
    _post(
        client,
        {
            'source_document_id': docs.waypoint2.document_id,
            'target_document_id': docs.waypoint3.document_id,
        },
        400,
    )


def test_merge_waypoint(client, session, docs):
    _post(
        client,
        {
            'source_document_id': docs.waypoint1.document_id,
            'target_document_id': docs.waypoint2.document_id,
        },
        200,
    )

    # check that associations have been transferred
    association_count = (
        session.query(Association)
        .filter(
            or_(
                Association.parent_document_id == docs.waypoint1.document_id,
                Association.child_document_id == docs.waypoint1.document_id,
            )
        )
        .count()
    )
    assert 0 == association_count
    association_log_count = (
        session.query(AssociationLog)
        .filter(
            or_(
                AssociationLog.parent_document_id == docs.waypoint1.document_id,
                AssociationLog.child_document_id == docs.waypoint1.document_id,
            )
        )
        .count()
    )
    assert 0 == association_count
    assert 0 == association_log_count

    association_route = session.get(
        Association, (docs.waypoint2.document_id, docs.route1.document_id)
    )
    assert association_route is not None

    # check that main waypoints are transferred
    session.refresh(docs.route1)
    assert docs.route1.main_waypoint_id == docs.waypoint2.document_id
    route_locale = docs.route1.locales[0]
    assert 'Mont Blanc' == route_locale.title_prefix

    # check that the redirection is set
    session.refresh(docs.waypoint1)
    assert docs.waypoint1.redirects_to == docs.waypoint2.document_id

    # check that a new version was created for the source document
    new_source_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == docs.waypoint1.document_id)
        .order_by(DocumentVersion.id.desc())
        .first()
    )
    assert new_source_version is not None
    assert (
        f'merged with {docs.waypoint2.document_id}'
        == new_source_version.history_metadata.comment
    )

    # check that the cache versions are updated
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 3)
    scenarios.check_cache_version(session, docs.route1.document_id, 2)

    # check that the feed entry is removed
    feed_count = (
        session.query(DocumentChange)
        .filter(DocumentChange.document_id == docs.waypoint1.document_id)
        .count()
    )
    assert 0 == feed_count


def test_merge_image(client, settings, docs):
    call = {'times': 0}

    @all_requests
    def image_service_mock(url, request):
        call['times'] += 1
        call['request.body'] = request.body.split('&')
        call['request.url'] = request.url
        return {'status_code': 200, 'content': ''}

    with HTTMock(image_service_mock):
        _post(
            client,
            {
                'source_document_id': docs.image1.document_id,
                'target_document_id': docs.image2.document_id,
            },
            200,
        )
        assert call['times'] == 1
        assert 'filenames=image1.1.jpg' in call['request.body']
        assert 'filenames=image1.jpg' in call['request.body']
        assert call['request.url'] == settings['image_backend.url'] + '/delete'


def test_merge_image_error_deleting_files(client, settings, docs):
    """Test that the merge request is also successful if the image files
    cannot be deleted.
    """
    call = {'times': 0}

    @all_requests
    def image_service_mock(url, request):
        call['times'] += 1
        call['request.body'] = request.body.split('&')
        call['request.url'] = request.url
        return {'status_code': 500, 'content': 'some random error'}

    with HTTMock(image_service_mock):
        _post(
            client,
            {
                'source_document_id': docs.image1.document_id,
                'target_document_id': docs.image2.document_id,
            },
            200,
        )
        assert call['times'] == 1
        assert 'filenames=image1.1.jpg' in call['request.body']
        assert 'filenames=image1.jpg' in call['request.body']
        assert call['request.url'] == settings['image_backend.url'] + '/delete'


def test_tags(client, session, docs):
    _post(
        client,
        {
            'source_document_id': docs.route1.document_id,
            'target_document_id': docs.route2.document_id,
        },
        200,
    )

    # Check tags and logs have been transfered from route1 to route2
    count = (
        session.query(DocumentTag)
        .filter(DocumentTag.document_id == docs.route2.document_id)
        .count()
    )
    assert count == 1
    count = (
        session.query(DocumentTagLog)
        .filter(DocumentTagLog.document_id == docs.route2.document_id)
        .count()
    )
    assert count == 1
