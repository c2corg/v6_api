from httmock import HTTMock

from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.image import Image
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import (  # noqa: F401
    _add_association,
    docs,
)
from c2corg_api.tests.views.test_document_trash import (  # noqa: F401
    _delete,
    _entry,
    _image,
    _image_service,
    _restore,
    outing_images,
)
from c2corg_api.tests.views.test_image_orphans import _embed
from c2corg_api.views.document import create_new_version


def _list(client, query='', username='moderator', status=200):
    return client.get(
        '/images/broken-embeds' + query,
        headers=auth_headers(username=username),
        status=status,
    )


def _broken(client, query=''):
    return [
        (e['document_id'], e['image_id'], e['reason'])
        for e in _list(client, query).json['embeds']
    ]


def test_broken_embeds(client, session, user_ids, docs, outing_images):  # noqa: F811
    _image_service.calls = []
    shown = _image(session, user_ids, 'contributor', 'collaborative', [], 'shown')
    # the deletion of an image finds the images merged into it by their
    # versions: the first one redirects already
    merged = Image(
        filename='merged.jpg',
        image_type='collaborative',
        redirects_to=shown.document_id,
        locales=[DocumentLocale(lang='en', title='merged')],
    )
    session.add(merged)
    session.flush()
    create_new_version(merged, user_ids['moderator'])
    photo_id = outing_images['photo'].document_id
    # route1: an image, a merged image (shows its target), a missing id,
    # another type of document
    embedded = [
        shown.document_id,
        merged.document_id,
        9999999,
        docs.waypoint1.document_id,
    ]
    _embed(session, docs.route1, *embedded)
    # a route: the title of its main waypoint before its title
    docs.route1.locales[0].title_prefix = 'Mont Blanc'
    # a merged document is not shown
    _embed(session, docs.route2, 9999998)
    docs.route2.redirects_to = docs.route1.document_id
    route1_id = docs.route1.document_id
    session.flush()
    assert _broken(client) == [
        (route1_id, docs.waypoint1.document_id, 'not_image'),
        (route1_id, 9999999, 'missing'),
    ]

    with HTTMock(_image_service):
        _delete(client, docs.outing2.document_id)
        # an image deleted on its own
        _delete(client, shown.document_id)
    # an image deleted with an outing, shown in route1 afterwards (as it can
    # be on prod, for images deleted before the embeds were stored)
    _embed(session, docs.route1, *embedded, photo_id)

    body = _list(client).json
    assert body['total'] == 5
    rows = [(e['image_id'], e['reason']) for e in body['embeds']]
    # the images that can be restored first, the first deleted first; the
    # image merged into a deleted one is restored with it
    assert rows[:3] == [
        (photo_id, 'deleted'),
        (shown.document_id, 'deleted'),
        (merged.document_id, 'deleted'),
    ]
    assert body['embeds'][2]['deleted'] == body['embeds'][1]['deleted']
    assert sorted(rows[3:]) == sorted(
        [(9999999, 'missing'), (docs.waypoint1.document_id, 'not_image')]
    )
    first = body['embeds'][0]
    assert first['document_id'] == route1_id
    assert first['document_type'] == 'r'
    assert first['title'] == 'Mont Blanc from the air'
    assert first['title_prefix'] == 'Mont Blanc'
    assert first['langs'] == ['en']
    outing_entry = _entry(session, docs.outing2.document_id)
    assert first['deleted']['entry_id'] == outing_entry.id
    assert first['deleted']['document_id'] == docs.outing2.document_id
    assert first['deleted']['document_type'] == 'o'
    assert first['deleted']['by']['forum_username'] == 'moderator'
    assert first['deleted']['expires_at'] > first['deleted']['deleted_at']
    not_image = next(e for e in body['embeds'] if e['reason'] == 'not_image')
    assert not_image['image_document_type'] == 'w'
    assert not_image['image_document_title'] == docs.waypoint1.locales[0].title
    assert first['image_document_title'] is None
    assert not_image['deleted'] is None

    # restored: shown again
    with HTTMock(_image_service):
        _restore(client, outing_entry.id)
    assert photo_id not in {e['image_id'] for e in _list(client).json['embeds']}


def test_broken_embeds_page(client, session, docs):  # noqa: F811
    _embed(session, docs.route1, 9999997, 9999998, 9999999)

    body = _list(client, '?offset=1&limit=1').json

    assert body['total'] == 3
    assert [e['image_id'] for e in body['embeds']] == [9999998]


def test_broken_embeds_reserved_to_the_moderators(client):
    _list(client, username='contributor', status=403)
    client.get('/images/broken-embeds', status=403)
