import datetime
from dataclasses import dataclass

import pytest

from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.favourite import Favourite, FavouriteFolder, FavouriteLog
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.tests import (
    assert_not_notified_es,
    assert_notified_es,
    auth_headers,
    post_json_with_contributor,
    send_json,
)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    contributor: User
    contributor2: User
    route1: Route
    route2: Route
    waypoint: Waypoint
    outing: Outing
    image: Image
    merged: Route
    folder2: FavouriteFolder


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor = session.get(User, user_ids['contributor'])
    contributor2 = session.get(User, user_ids['contributor2'])

    route1 = Route(
        activities=['skitouring'],
        locales=[
            RouteLocale(lang='en', title='Route1', title_prefix='Summit'),
            RouteLocale(lang='fr', title='Voie1', title_prefix='Sommet'),
        ],
    )
    route2 = Route(
        activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route2')]
    )
    waypoint = Waypoint(
        waypoint_type='summit',
        elevation=2203,
        locales=[WaypointLocale(lang='it', title='Monte')],
    )
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        locales=[OutingLocale(lang='en', title='Outing')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'
        ),
    )
    image = Image(
        filename='image.jpg', locales=[DocumentLocale(lang='en', title='Img')]
    )
    session.add_all([route1, route2, waypoint, outing, image])
    session.flush()
    merged = Route(
        activities=['hiking'],
        redirects_to=route1.document_id,
        locales=[RouteLocale(lang='en', title='Merged')],
    )
    session.add(merged)
    folder2 = FavouriteFolder(user_id=contributor2.id, name='Theirs')
    session.add(folder2)
    session.flush()

    session.add(
        Favourite(
            user_id=contributor2.id,
            document_id=route2.document_id,
            document_type=ROUTE_TYPE,
            folder_id=folder2.id,
        )
    )
    session.flush()
    return Docs(
        contributor=contributor,
        contributor2=contributor2,
        route1=route1,
        route2=route2,
        waypoint=waypoint,
        outing=outing,
        image=image,
        merged=merged,
        folder2=folder2,
    )


def _favourite(session, user_id, document_id):
    session.expire_all()
    return (
        session.query(Favourite)
        .filter(Favourite.user_id == user_id)
        .filter(Favourite.document_id == document_id)
        .one_or_none()
    )


def _logs(session, user_id, document_id):
    return (
        session.query(FavouriteLog.document_type, FavouriteLog.is_creation)
        .filter(FavouriteLog.user_id == user_id)
        .filter(FavouriteLog.document_id == document_id)
        .order_by(FavouriteLog.id)
        .all()
    )


def _folder(session, user_id, name, position=0):
    folder = FavouriteFolder(user_id=user_id, name=name, position=position)
    session.add(folder)
    session.flush()
    return folder


def _get(client, url, username='contributor', status=200):
    return client.get(url, headers=auth_headers(username=username), status=status)


@pytest.mark.parametrize(
    'url',
    [
        '/favourites/add',
        '/favourites/remove',
        '/favourites/move',
        '/favourites/folders',
        '/favourites/folders/order',
        '/tags/add',
        '/tags/remove',
    ],
)
def test_writes_need_a_user(client, url):
    send_json(client, 'post', url, {}, status=403)


@pytest.mark.parametrize(
    'url', ['/favourites', '/favourites/folders', '/favourites/has/1', '/tags/has/1']
)
def test_reads_need_a_user(client, url):
    client.get(url, status=403)


@pytest.mark.parametrize('url', ['/favourites/add', '/tags/add'])
def test_add_route(client, session, queue_config, docs, url):
    body = {'document_id': docs.route1.document_id}
    post_json_with_contributor(client, url, body)

    favourite = _favourite(session, docs.contributor.id, docs.route1.document_id)
    assert favourite.document_type == ROUTE_TYPE
    assert favourite.folder_id is None
    assert favourite.created_at is not None
    assert _logs(session, docs.contributor.id, docs.route1.document_id) == [
        (ROUTE_TYPE, True)
    ]
    assert_notified_es(queue_config)

    # already one: nothing changes
    post_json_with_contributor(client, url, body)
    assert _logs(session, docs.contributor.id, docs.route1.document_id) == [
        (ROUTE_TYPE, True)
    ]
    assert_not_notified_es(queue_config)


@pytest.mark.parametrize(
    ('name', 'document_type'), [('waypoint', WAYPOINT_TYPE), ('outing', OUTING_TYPE)]
)
def test_add_other_types(client, session, queue_config, docs, name, document_type):
    document_id = getattr(docs, name).document_id
    post_json_with_contributor(client, '/favourites/add', {'document_id': document_id})

    favourite = _favourite(session, docs.contributor.id, document_id)
    assert favourite.document_type == document_type
    assert _logs(session, docs.contributor.id, document_id) == [(document_type, True)]
    # only the routes have their favourites in the search index
    assert_not_notified_es(queue_config)


@pytest.mark.parametrize('name', ['image', 'merged'])
def test_add_refused_documents(client, docs, name):
    body = {'document_id': getattr(docs, name).document_id}
    response = send_json(
        client,
        'post',
        '/favourites/add',
        body,
        headers=auth_headers(username='contributor'),
        status=400,
    )
    assert response.json['errors'][0]['name'] == 'document_id'
    assert docs.image.type == IMAGE_TYPE


def test_add_unknown_document(client):
    response = send_json(
        client,
        'post',
        '/favourites/add',
        {'document_id': 9999999},
        headers=auth_headers(username='contributor'),
        status=400,
    )
    assert response.json['errors'][0]['name'] == 'document_id'


def test_add_in_folder(client, session, docs):
    folder_a = _folder(session, docs.contributor.id, 'A')
    folder_b = _folder(session, docs.contributor.id, 'B', 1)
    body = {'document_id': docs.route1.document_id, 'folder_id': folder_a.id}
    post_json_with_contributor(client, '/favourites/add', body)
    favourite = _favourite(session, docs.contributor.id, docs.route1.document_id)
    assert favourite.folder_id == folder_a.id

    # added again in another folder: moved, not logged again
    body['folder_id'] = folder_b.id
    post_json_with_contributor(client, '/favourites/add', body)
    session.expire_all()
    favourite = _favourite(session, docs.contributor.id, docs.route1.document_id)
    assert favourite.folder_id == folder_b.id
    assert len(_logs(session, docs.contributor.id, docs.route1.document_id)) == 1

    # added again without folder: the folder is kept
    post_json_with_contributor(
        client, '/favourites/add', {'document_id': docs.route1.document_id}
    )
    session.expire_all()
    favourite = _favourite(session, docs.contributor.id, docs.route1.document_id)
    assert favourite.folder_id == folder_b.id


def test_add_in_folder_of_another_user(client, session, docs):
    body = {'document_id': docs.route1.document_id, 'folder_id': docs.folder2.id}
    response = send_json(
        client,
        'post',
        '/favourites/add',
        body,
        headers=auth_headers(username='contributor'),
        status=400,
    )
    assert response.json['errors'][0]['name'] == 'folder_id'
    assert _favourite(session, docs.contributor.id, docs.route1.document_id) is None


@pytest.mark.parametrize('url', ['/favourites/remove', '/tags/remove'])
def test_remove(client, session, queue_config, docs, url):
    body = {'document_id': docs.route2.document_id}
    post_json_with_contributor(client, url, body, username='contributor2')

    assert _favourite(session, docs.contributor2.id, docs.route2.document_id) is None
    assert _logs(session, docs.contributor2.id, docs.route2.document_id) == [
        (ROUTE_TYPE, False)
    ]
    assert_notified_es(queue_config)

    # not one any more: nothing changes
    post_json_with_contributor(client, url, body, username='contributor2')
    assert len(_logs(session, docs.contributor2.id, docs.route2.document_id)) == 1
    assert_not_notified_es(queue_config)


def test_remove_other_type(client, session, queue_config, docs):
    document_id = docs.outing.document_id
    session.add(
        Favourite(
            user_id=docs.contributor.id,
            document_id=document_id,
            document_type=OUTING_TYPE,
        )
    )
    session.flush()
    post_json_with_contributor(
        client, '/favourites/remove', {'document_id': document_id}
    )
    assert _favourite(session, docs.contributor.id, document_id) is None
    assert _logs(session, docs.contributor.id, document_id) == [(OUTING_TYPE, False)]
    assert_not_notified_es(queue_config)


def test_move(client, session, docs):
    folder = _folder(session, docs.contributor2.id, 'Mine')
    route_id = docs.route2.document_id
    body = {'document_id': route_id, 'folder_id': folder.id}
    post_json_with_contributor(
        client, '/favourites/move', body, username='contributor2'
    )
    session.expire_all()
    assert _favourite(session, docs.contributor2.id, route_id).folder_id == folder.id

    body = {'document_id': route_id, 'folder_id': None}
    post_json_with_contributor(
        client, '/favourites/move', body, username='contributor2'
    )
    session.expire_all()
    assert _favourite(session, docs.contributor2.id, route_id).folder_id is None
    # a move is not logged
    assert _logs(session, docs.contributor2.id, route_id) == []


def test_move_not_a_favourite(client, docs):
    body = {'document_id': docs.route1.document_id}
    post_json_with_contributor(client, '/favourites/move', body, status=400)


def test_move_to_folder_of_another_user(client, session, docs):
    folder = _folder(session, docs.contributor.id, 'Not theirs')
    body = {'document_id': docs.route2.document_id, 'folder_id': folder.id}
    post_json_with_contributor(
        client, '/favourites/move', body, username='contributor2', status=400
    )


def test_has(client, docs):
    url = f'/favourites/has/{docs.route2.document_id}'
    body = _get(client, url, username='contributor2').json
    assert body == {'favourite': True, 'folder_id': docs.folder2.id}
    body = _get(client, url).json
    assert body == {'favourite': False, 'folder_id': None}


def test_has_former_route(client, docs):
    url = f'/tags/has/{docs.route2.document_id}'
    assert _get(client, url, username='contributor2').json == {'todo': True}
    assert _get(client, url).json == {'todo': False}


def test_list(client, session, docs):
    user_id = docs.contributor.id
    folder = _folder(session, user_id, 'Later', 1)
    first = _folder(session, user_id, 'First', 0)
    for day, (document, document_type, folder_id) in enumerate(
        (
            (docs.outing, OUTING_TYPE, None),
            (docs.route1, ROUTE_TYPE, folder.id),
            (docs.waypoint, WAYPOINT_TYPE, None),
        ),
        start=1,
    ):
        session.add(
            Favourite(
                user_id=user_id,
                document_id=document.document_id,
                document_type=document_type,
                folder_id=folder_id,
                created_at=datetime.datetime(2026, 1, day, tzinfo=datetime.UTC),
            )
        )
    session.flush()

    body = _get(client, '/favourites?pl=fr').json
    favourites = {f['document_id']: f for f in body['favourites']}
    assert set(favourites) == {
        docs.route1.document_id,
        docs.waypoint.document_id,
        docs.outing.document_id,
    }
    assert favourites[docs.route1.document_id] == {
        'document_id': docs.route1.document_id,
        'type': ROUTE_TYPE,
        'folder_id': folder.id,
        'created_at': favourites[docs.route1.document_id]['created_at'],
        'lang': 'fr',
        'title': 'Voie1',
        'title_prefix': 'Sommet',
    }
    # no locale in the language: the best other one
    assert favourites[docs.waypoint.document_id]['lang'] == 'it'
    assert favourites[docs.waypoint.document_id]['title_prefix'] is None
    assert favourites[docs.outing.document_id]['title'] == 'Outing'
    # the latest first
    assert [f['type'] for f in body['favourites']] == [
        WAYPOINT_TYPE,
        ROUTE_TYPE,
        OUTING_TYPE,
    ]
    assert [(f['id'], f['name'], f['position']) for f in body['folders']] == [
        (first.id, 'First', 0),
        (folder.id, 'Later', 1),
    ]

    body = _get(client, '/favourites?pl=en').json
    route = next(f for f in body['favourites'] if f['type'] == ROUTE_TYPE)
    assert (route['lang'], route['title']) == ('en', 'Route1')


def test_list_in_the_language_of_the_user(client, session, docs):
    docs.contributor.lang = 'fr'
    session.add(
        Favourite(
            user_id=docs.contributor.id,
            document_id=docs.route1.document_id,
            document_type=ROUTE_TYPE,
        )
    )
    session.flush()
    body = _get(client, '/favourites').json
    assert body['favourites'][0]['title'] == 'Voie1'


def test_list_only_own(client, docs):
    body = _get(client, '/favourites').json
    assert body == {'favourites': [], 'folders': []}


def test_create_folders(client, session, docs):
    answer = post_json_with_contributor(
        client, '/favourites/folders', {'name': ' Summer '}
    )
    assert answer['name'] == 'Summer'
    assert answer['position'] == 0
    assert answer['created_at']
    answer = post_json_with_contributor(
        client, '/favourites/folders', {'name': 'Winter'}
    )
    assert answer['position'] == 1

    # the same name as another folder of the user
    post_json_with_contributor(
        client, '/favourites/folders', {'name': 'Winter'}, status=400
    )
    # the same name as a folder of another user
    post_json_with_contributor(client, '/favourites/folders', {'name': 'Theirs'})

    body = _get(client, '/favourites/folders').json
    assert [f['name'] for f in body['folders']] == ['Summer', 'Winter', 'Theirs']


@pytest.mark.parametrize(
    ('name', 'status'), [('', 422), ('   ', 400), ('x' * 101, 422)]
)
def test_create_folder_invalid_name(client, name, status):
    post_json_with_contributor(
        client, '/favourites/folders', {'name': name}, status=status
    )


def test_rename_folder(client, session, docs):
    folder = _folder(session, docs.contributor.id, 'Old')
    _folder(session, docs.contributor.id, 'Other', 1)
    headers = auth_headers(username='contributor')
    url = f'/favourites/folders/{folder.id}'

    answer = send_json(client, 'put', url, {'name': 'New'}, headers=headers).json
    assert (answer['id'], answer['name']) == (folder.id, 'New')
    # its own name again
    send_json(client, 'put', url, {'name': 'New'}, headers=headers)
    send_json(client, 'put', url, {'name': 'Other'}, headers=headers, status=400)


def test_rename_folder_of_another_user(client, docs):
    url = f'/favourites/folders/{docs.folder2.id}'
    headers = auth_headers(username='contributor')
    send_json(client, 'put', url, {'name': 'Mine'}, headers=headers, status=404)


def test_delete_folder(client, session, docs):
    folder_id = docs.folder2.id
    url = f'/favourites/folders/{folder_id}'
    headers = auth_headers(username='contributor2')
    client.delete(url, headers=headers, status=200)
    session.expire_all()

    assert session.get(FavouriteFolder, folder_id) is None
    # its favourites are kept, in the main list
    favourite = _favourite(session, docs.contributor2.id, docs.route2.document_id)
    assert favourite.folder_id is None


def test_delete_folder_of_another_user(client, session, docs):
    url = f'/favourites/folders/{docs.folder2.id}'
    headers = auth_headers(username='contributor')
    client.delete(url, headers=headers, status=404)
    session.expire_all()
    assert session.get(FavouriteFolder, docs.folder2.id) is not None


def test_order_folders(client, session, docs):
    a = _folder(session, docs.contributor.id, 'A', 0)
    b = _folder(session, docs.contributor.id, 'B', 1)
    c = _folder(session, docs.contributor.id, 'C', 2)

    answer = post_json_with_contributor(
        client, '/favourites/folders/order', {'folder_ids': [c.id, a.id]}
    )
    assert [(f['id'], f['position']) for f in answer['folders']] == [
        (c.id, 0),
        (a.id, 1),
        (b.id, 2),
    ]


@pytest.mark.parametrize('case', ['twice', 'another user', 'unknown'])
def test_order_folders_refused(client, session, docs, case):
    a = _folder(session, docs.contributor.id, 'A', 0)
    folder_ids = {
        'twice': [a.id, a.id],
        'another user': [docs.folder2.id],
        'unknown': [9999999],
    }[case]
    post_json_with_contributor(
        client, '/favourites/folders/order', {'folder_ids': folder_ids}, status=400
    )
    session.expire_all()
    assert session.get(FavouriteFolder, docs.folder2.id).position == 0
