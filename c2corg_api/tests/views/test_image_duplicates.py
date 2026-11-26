import datetime

import pytest
from httmock import HTTMock

from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.image_duplicate import DismissedImageDuplicate
from c2corg_api.models.image_embed import ImageEmbed
from c2corg_api.tests import auth_headers, reset_cache_key
from c2corg_api.tests.views.test_document_delete import (  # noqa: F401
    _add_association,
    docs,
)
from c2corg_api.tests.views.test_document_trash import (
    _delete,
    _entry,
    _image_service,
    _restore,
)
from c2corg_api.views.document import create_new_version

TAKEN = datetime.datetime(2026, 7, 14, 10, 0, tzinfo=datetime.UTC)


def _list(client, query='', username='moderator', status=200):
    return client.get(
        '/images/duplicates' + query,
        headers=auth_headers(username=username),
        status=status,
    )


def _dismiss(client, body, username='moderator', status=200):
    return client.post_json(
        '/images/duplicates/dismiss',
        body,
        headers=auth_headers(username=username),
        status=status,
    )


def _file(session, user_ids, username, image_type, linked_to, title, **file):
    """Add an image of the given file (by default the copy of TAKEN)."""
    image = Image(
        filename=f'{title}.jpg',
        image_type=image_type,
        file_size=file.get('file_size', 1234567),
        width=file.get('width', 4000),
        height=file.get('height', 3000),
        date_time=file.get('date_time', TAKEN),
        locales=[DocumentLocale(lang='en', title=title)],
    )
    session.add(image)
    session.flush()
    create_new_version(image, user_ids[username])
    for document in linked_to:
        _add_association(session, user_ids, document, image)
    session.flush()
    return image


@pytest.fixture
def copies(session, user_ids, docs):  # noqa: F811
    """A photo of an outing also uploaded to a route, and one twice on a route."""
    outing, route = docs.outing2, docs.route1
    personal = _file(session, user_ids, 'contributor', 'personal', [outing], 'personal')
    collaborative = _file(
        session, user_ids, 'contributor', 'collaborative', [route], 'collaborative'
    )
    twice = [
        _file(
            session,
            user_ids,
            'contributor2',
            'collaborative',
            [route],
            f'twice{n}',
            file_size=555,
            date_time=None,
        )
        for n in (1, 2)
    ]
    # not copies: another date, another size
    _file(
        session,
        user_ids,
        'contributor',
        'personal',
        [outing],
        'other day',
        date_time=TAKEN + datetime.timedelta(days=1),
    )
    _file(
        session,
        user_ids,
        'contributor',
        'personal',
        [outing],
        'other size',
        file_size=1234568,
    )
    return personal, collaborative, twice


def test_duplicate_images(client, docs, copies):  # noqa: F811
    personal, collaborative, twice = copies

    body = _list(client).json

    # the last uploaded first
    assert body['total'] == 2
    first, second = body['sets']
    assert [i['document_id'] for i in first['images']] == [
        twice[0].document_id,
        twice[1].document_id,
    ]
    assert first['same_document'] is True
    assert second['same_document'] is False
    images = second['images']
    assert [i['document_id'] for i in images] == [
        personal.document_id,
        collaborative.document_id,
    ]
    assert images[0]['image_type'] == 'personal'
    assert images[0]['title'] == 'personal'
    assert images[0]['author']['forum_username'] == 'contributor'
    assert images[0]['created_at'] is not None
    assert images[0]['file_size'] == 1234567
    assert images[0]['date_time'] == TAKEN.isoformat()
    assert images[0]['documents'] == [
        {
            'document_id': docs.outing2.document_id,
            'document_type': 'o',
            'title': docs.outing2.locales[0].title,
        }
    ]
    assert images[1]['documents'][0]['document_type'] == 'r'


def test_duplicate_images_filter_and_page(client, copies):
    personal, collaborative, twice = copies

    body = _list(client, '?same_document=true').json
    assert body['total'] == 1
    assert body['sets'][0]['same_document'] is True

    body = _list(client, '?offset=1&limit=1').json
    assert body['total'] == 2
    assert [i['document_id'] for i in body['sets'][0]['images']] == [
        personal.document_id,
        collaborative.document_id,
    ]
    # past the last page
    body = _list(client, '?offset=5').json
    assert body == {'total': 2, 'sets': []}


def test_merged_image_not_listed(client, session, copies):
    personal, collaborative, twice = copies
    # listed first: the sets are cached, the merge shows at once all the same
    assert _list(client).json['total'] == 2
    personal.redirects_to = collaborative.document_id
    session.flush()

    body = _list(client).json

    assert body['total'] == 1


def test_dismiss_a_set(client, session, copies):
    personal, collaborative, twice = copies

    body = _dismiss(
        client, {'image_ids': [collaborative.document_id, personal.document_id]}
    ).json

    assert body == {'dismissed': 1}
    row = session.query(DismissedImageDuplicate).one()
    assert (row.image1_id, row.image2_id) == (
        personal.document_id,
        collaborative.document_id,
    )
    assert row.dismissed_by is not None
    assert _list(client).json['total'] == 1
    # again: nothing new
    _dismiss(client, {'image_ids': [personal.document_id, collaborative.document_id]})
    assert session.query(DismissedImageDuplicate).count() == 1


def test_dismiss_one_image_of_a_set(client, session, user_ids, docs, copies):  # noqa: F811
    personal, collaborative, twice = copies
    third = _file(session, user_ids, 'contributor', 'personal', [docs.outing2], '3')

    # the third is not a copy of the other two: the set of two stays
    body = _dismiss(
        client,
        {
            'image_ids': [third.document_id],
            'against': [personal.document_id, collaborative.document_id],
        },
    ).json
    assert body == {'dismissed': 2}
    sets = _list(client).json['sets']
    assert len(sets) == 2
    assert third.document_id in [i['document_id'] for i in sets[0]['images']]

    # the last pair dismissed: the set is hidden
    _dismiss(client, {'image_ids': [personal.document_id, collaborative.document_id]})
    assert _list(client).json['total'] == 1

    # a new copy shows the set again, once the cached sets expire
    _file(session, user_ids, 'contributor', 'personal', [docs.outing2], '4')
    assert _list(client).json['total'] == 1
    reset_cache_key()
    assert _list(client).json['total'] == 2


def test_dismiss_invalid(client, docs, copies):  # noqa: F811
    personal, collaborative, twice = copies

    _dismiss(client, {'image_ids': [personal.document_id]}, status=400)
    _dismiss(
        client,
        {'image_ids': [personal.document_id], 'against': [personal.document_id]},
        status=400,
    )
    body = _dismiss(
        client,
        {'image_ids': [personal.document_id, docs.route1.document_id]},
        status=400,
    ).json
    assert str(docs.route1.document_id) in body['errors'][0]['description']
    _dismiss(client, {}, status=422)


def test_duplicate_images_reserved_to_the_moderators(client, copies):
    personal, collaborative, twice = copies
    _list(client, username='contributor', status=403)
    client.get('/images/duplicates', status=403)
    _dismiss(
        client,
        {'image_ids': [personal.document_id, collaborative.document_id]},
        username='contributor',
        status=403,
    )


def test_dismissed_pairs_kept_by_the_soft_delete(client, session, copies):
    personal, collaborative, twice = copies
    _dismiss(client, {'image_ids': [personal.document_id, collaborative.document_id]})
    _image_service.calls = []

    with HTTMock(_image_service):
        _delete(client, collaborative.document_id)
        assert session.query(DismissedImageDuplicate).count() == 0
        _restore(client, _entry(session, collaborative.document_id).id)

    row = session.query(DismissedImageDuplicate).one()
    assert row.image2_id == collaborative.document_id
    assert _list(client).json['total'] == 1


def test_texts_showing_an_image(client, session, user_ids, docs, copies):  # noqa: F811
    personal, collaborative, twice = copies
    route_locale = docs.route1.locales[0]
    # an older copy already merged into the collaborative image
    merged = _image_file(session, user_ids, 'old copy', file_size=1)
    merged.redirects_to = collaborative.document_id
    session.add_all(
        [
            ImageEmbed(
                document_locale_id=route_locale.id,
                image_id=personal.document_id,
                document_id=docs.route1.document_id,
                lang=route_locale.lang,
            ),
            ImageEmbed(
                document_locale_id=route_locale.id,
                image_id=merged.document_id,
                document_id=docs.route1.document_id,
                lang=route_locale.lang,
            ),
        ]
    )
    session.flush()

    images = _list(client, '?offset=1').json['sets'][0]['images']

    expected = {
        'document_id': docs.route1.document_id,
        'document_type': 'r',
        'lang': route_locale.lang,
        'title': route_locale.title,
    }
    assert images[0]['embedded_in'] == [{**expected, 'image_id': personal.document_id}]
    assert images[1]['embedded_in'] == [{**expected, 'image_id': merged.document_id}]


def _image_file(session, user_ids, title, **file):
    return _file(session, user_ids, 'contributor', 'collaborative', [], title, **file)


def _uploaded_at(session, image, at):
    """Move the first version of an image to another time."""
    version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == image.document_id)
        .order_by(DocumentVersion.id)
        .first()
    )
    version.history_metadata.written_at = at
    session.flush()


@pytest.mark.parametrize(('days_apart', 'listed'), [(6, True), (8, False)])
def test_without_exif_date_by_other_users(
    client, session, user_ids, days_apart, listed
):
    # no EXIF date: the same size and dimensions match by chance more often
    first = _file(session, user_ids, 'contributor', 'personal', [], 'a', date_time=None)
    second = _file(
        session, user_ids, 'contributor2', 'personal', [], 'b', date_time=None
    )
    _uploaded_at(session, first, TAKEN)
    _uploaded_at(session, second, TAKEN + datetime.timedelta(days=days_apart))

    body = _list(client).json

    assert body['total'] == (1 if listed else 0)


def test_without_exif_date_by_one_user(client, session, user_ids):
    first = _file(session, user_ids, 'contributor', 'personal', [], 'a', date_time=None)
    second = _file(
        session, user_ids, 'contributor', 'personal', [], 'b', date_time=None
    )
    _uploaded_at(session, first, TAKEN)
    _uploaded_at(session, second, TAKEN + datetime.timedelta(days=400))

    assert _list(client).json['total'] == 1


def test_texts_linking_to_an_image(client, session, user_ids, docs, copies):  # noqa: F811
    from c2corg_api.models.document_link import DocumentLink

    personal, collaborative, twice = copies
    route_locale = docs.route1.locales[0]
    common = {
        'document_locale_id': route_locale.id,
        'document_id': docs.route1.document_id,
        'lang': route_locale.lang,
        'is_url': False,
    }
    session.add_all(
        [
            DocumentLink(
                **common, target_id=personal.document_id, target_type='images'
            ),
            # a link to a route: does not show the image
            DocumentLink(
                **common, target_id=collaborative.document_id, target_type='routes'
            ),
        ]
    )
    session.flush()

    images = _list(client, '?offset=1').json['sets'][0]['images']

    assert images[0]['linked_from'] == [
        {
            'document_id': docs.route1.document_id,
            'document_type': 'r',
            'lang': route_locale.lang,
            'title': route_locale.title,
            'image_id': personal.document_id,
        }
    ]
    assert images[1]['linked_from'] == []
