from dataclasses import dataclass
from json import loads

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import assert_errors_contain, auth_headers, send_json
from c2corg_api.views.document import create_new_version, update_version

PREFIX = '/documents/revert'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    initial_route1_geometry: DocumentGeometry
    route1: Route


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
        elevation=4810,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635957 5723605)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont Blanc',
                description='...',
                summary='The highest point in Europe',
            )
        ],
    )
    session.add(waypoint2)
    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=2432,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635958 5723606)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont de Grange',
                description='...',
                summary='Some nice peak',
            )
        ],
    )
    session.add(waypoint3)
    session.flush()

    initial_route1_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )

    route1 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        main_waypoint_id=waypoint2.document_id,
        geometry=initial_route1_geometry,
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
    session.flush()

    create_new_version(waypoint1, contributor_id)
    create_new_version(waypoint2, contributor_id)
    create_new_version(route1, contributor_id)
    update_feed_document_create(waypoint1, contributor_id)
    update_feed_document_create(waypoint2, contributor_id)
    update_feed_document_create(route1, contributor_id)
    session.flush()

    association = Association.create(parent_document=waypoint1, child_document=route1)
    session.add(association)
    session.add(association.get_log(contributor_id))
    association = Association.create(parent_document=waypoint2, child_document=route1)
    session.add(association)
    session.add(association.get_log(contributor_id))
    session.flush()

    waypoint2.elevation = 8848
    for locale in waypoint2.locales:
        if locale.lang == 'en':
            locale.title = 'Mount Everest'
            locale.summary = 'The highest point in the world'
    waypoint2.geometry.geom = 'SRID=3857;POINT(0 0)'

    route1.activities = ['skitouring', 'hiking']
    route1.elevation_max = 4500
    route1.main_waypoint_id = waypoint3.document_id
    for locale in route1.locales:
        if locale.lang == 'fr':
            locale.title = 'Some new route name'
    route1.geometry.geom = 'SRID=3857;POINT(0 0)'
    session.flush()

    update_version(
        waypoint2,
        contributor_id,
        'new version',
        [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG],
        ['en'],
    )
    update_version(
        route1,
        contributor_id,
        'new version',
        [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG],
        ['fr'],
    )
    session.flush()

    association = Association.create(parent_document=waypoint3, child_document=route1)
    session.add(association)
    session.add(association.get_log(contributor_id))
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        initial_route1_geometry=initial_route1_geometry,
        route1=route1,
    )

    # TODO what if former main waypoint is deassociated?


def test_revert_unauthorized(client):
    send_json(client, 'post', PREFIX, {}, status=403)

    headers = auth_headers(username='contributor')
    send_json(client, 'post', PREFIX, {}, headers=headers, status=403)


def test_revert_invalid_document_id(client):
    request_body = {'document_id': -1, 'lang': 'en', 'version_id': 123456}

    headers = auth_headers(username='moderator')
    send_json(client, 'post', PREFIX, request_body, status=400, headers=headers)


def test_revert_invalid_version_id(client, docs):
    document_id = docs.waypoint2.document_id
    lang = 'en'
    version_id = 123456
    request_body = {
        'document_id': document_id,
        'lang': lang,
        'version_id': version_id,
    }

    headers = auth_headers(username='moderator')
    response = send_json(
        client, 'post', PREFIX, request_body, status=400, headers=headers
    )
    assert_errors_contain(
        response.json,
        'Bad Request',
        f'Unknown version {document_id}/{lang}/{version_id}',
    )


def test_revert_latest_version_id(client, session, docs):
    document_id = docs.waypoint2.document_id
    lang = 'en'
    # Get version id of the latest version of the document:
    (version_id,) = (
        session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .order_by(DocumentVersion.id.desc())
        .first()
    )
    request_body = {
        'document_id': document_id,
        'lang': lang,
        'version_id': version_id,
    }

    headers = auth_headers(username='moderator')
    response = send_json(
        client, 'post', PREFIX, request_body, status=400, headers=headers
    )
    assert_errors_contain(
        response.json,
        'Bad Request',
        f'Version {document_id}/{lang}/{version_id} is already the latest one',
    )


def test_revert_waypoint(client, session, docs):
    document_id = docs.waypoint2.document_id
    lang = 'en'
    # Get version id of the first version of the document:
    (version_id,) = (
        session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .order_by(DocumentVersion.id.asc())
        .first()
    )

    initial_count = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .count()
    )

    request_body = {
        'document_id': document_id,
        'lang': lang,
        'version_id': version_id,
    }

    headers = auth_headers(username='moderator')
    send_json(client, 'post', PREFIX, request_body, status=200, headers=headers)

    response = client.get('/waypoints/' + str(document_id), status=200)
    body = response.json
    assert body['elevation'] == 4810
    geom = loads(body['geometry']['geom'])
    assert geom['coordinates'][0] == 635957
    assert geom['coordinates'][1] == 5723605
    for locale in body['locales']:
        if locale['lang'] == lang:
            assert locale['summary'] == 'The highest point in Europe'

    # check a new version has been created
    count = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .filter(DocumentVersion.lang == lang)
        .count()
    )
    assert count == initial_count + 1


def test_revert_route(client, session, docs):
    route_id = docs.route1.document_id
    route_lang = 'fr'
    # Get version id of the first version of the document:
    (route_version_id,) = (
        session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == route_id)
        .filter(DocumentVersion.lang == route_lang)
        .order_by(DocumentVersion.id.asc())
        .first()
    )

    request_body = {
        'document_id': route_id,
        'lang': route_lang,
        'version_id': route_version_id,
    }

    headers = auth_headers(username='moderator')
    send_json(client, 'post', PREFIX, request_body, status=200, headers=headers)

    response = client.get('/routes/' + str(route_id), status=200)
    body = response.json
    assert body['elevation_max'] == 1500
    assert body['activities'] == ['skitouring']
    for locale in body['locales']:
        if locale['lang'] == route_lang:
            assert locale['title'] == 'Mont Blanc du ciel'
            assert locale['title_prefix'] == 'Mount Everest'

    # Now revert the main waypoint as well and check the title prefix
    # of the route has been updated:
    waypoint_id = docs.waypoint2.document_id
    waypoint_lang = 'en'
    # Get version id of the first version of the document:
    (waypoint_version_id,) = (
        session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == waypoint_id)
        .filter(DocumentVersion.lang == waypoint_lang)
        .order_by(DocumentVersion.id.asc())
        .first()
    )

    request_body = {
        'document_id': waypoint_id,
        'lang': waypoint_lang,
        'version_id': waypoint_version_id,
    }

    headers = auth_headers(username='moderator')
    send_json(client, 'post', PREFIX, request_body, status=200, headers=headers)

    response = client.get('/routes/' + str(route_id), status=200)
    body = response.json
    for locale in body['locales']:
        if locale['lang'] == route_lang:
            assert locale['title'] == 'Mont Blanc du ciel'
            assert locale['title_prefix'] == 'Mont Blanc'
