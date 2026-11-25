import pytest

from c2corg_api.models.association import Association
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import (  # noqa: F401
    _add_association,
    docs,
)
from c2corg_api.tests.views.test_document_trash import _image


def _list(client, query='', username='moderator', status=200):
    return client.get(
        '/images/orphans' + query,
        headers=auth_headers(username=username),
        status=status,
    )


@pytest.fixture
def orphans(session, user_ids, docs):  # noqa: F811
    first = _image(session, user_ids, 'contributor', 'personal', [], 'first')
    second = _image(session, user_ids, 'contributor2', 'collaborative', [], 'second')
    # an image whose link was removed
    unlinked = _image(
        session, user_ids, 'contributor', 'collaborative', [docs.route1], 'unlinked'
    )
    association = (
        session.query(Association)
        .filter_by(child_document_id=unlinked.document_id)
        .one()
    )
    session.add(association.get_log(user_ids['moderator'], is_creation=False))
    session.delete(association)
    session.flush()
    return first, second, unlinked


def test_orphan_images(client, user_ids, docs, orphans):  # noqa: F811
    first, second, unlinked = orphans

    body = _list(client).json

    # the linked image of the documents is not listed; the last created first
    assert body['total'] == 3
    images = body['images']
    assert [i['document_id'] for i in images] == [
        unlinked.document_id,
        second.document_id,
        first.document_id,
    ]
    assert images[1]['image_type'] == 'collaborative'
    assert images[1]['title'] == 'second'
    assert images[1]['filename'] == 'second.jpg'
    assert images[1]['author']['forum_username'] == 'contributor2'
    assert images[1]['created_at'] is not None
    assert images[1]['last_unlink'] is None
    last_unlink = images[0]['last_unlink']
    assert last_unlink['document_id'] == docs.route1.document_id
    assert last_unlink['document_type'] == 'r'
    assert last_unlink['by']['forum_username'] == 'moderator'


def test_orphan_images_filter_and_page(client, docs, orphans):  # noqa: F811
    first, second, unlinked = orphans

    body = _list(client, '?image_type=collaborative&offset=1&limit=1').json

    assert body['total'] == 2
    assert [i['document_id'] for i in body['images']] == [second.document_id]
    _list(client, '?image_type=nope', status=422)


def test_orphan_images_reserved_to_the_moderators(client):
    _list(client, username='contributor', status=403)
    client.get('/images/orphans', status=403)


def _embed(session, document, *image_ids):
    """Show these images in the text of the first locale of a document."""
    from c2corg_api.views.markdown import update_image_embeds

    locale = document.locales[0]
    locale.description = 'Text\n\n' + '\n\n'.join(
        f'[img={image_id} right/]' for image_id in image_ids
    )
    session.flush()
    update_image_embeds([locale])
    session.flush()


def test_orphan_images_embedded_in(client, session, docs, orphans):  # noqa: F811
    first, second, unlinked = orphans
    _embed(session, docs.route1, unlinked.document_id)
    # the image itself and a merged document are not other shown documents
    _embed(session, first, first.document_id)
    _embed(session, docs.route2, first.document_id)
    docs.route2.redirects_to = docs.route1.document_id
    session.flush()

    images = {i['document_id']: i for i in _list(client).json['images']}

    assert images[unlinked.document_id]['embedded_in'] == [
        {
            'document_id': docs.route1.document_id,
            'document_type': 'r',
            'title': 'Mont Blanc from the air',
            'langs': ['en'],
        }
    ]
    assert images[first.document_id]['embedded_in'] == []
    assert images[second.document_id]['embedded_in'] == []
