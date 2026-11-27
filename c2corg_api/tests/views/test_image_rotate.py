from dataclasses import dataclass
from unittest.mock import Mock, patch

import pytest

from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import ArchiveImage, Image
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.views.document import create_new_version

URL = '/images/rotate'
BACKEND = 'c2corg_api.views.image_rotate.requests.post'


@dataclass
class Docs:
    """The images of the tests, built by `docs`."""

    collaborative: Image
    personal: Image
    svg: Image


def _image(session, author_id, filename, image_type):
    image = Image(filename=filename, image_type=image_type, activities=['hiking'])
    image.locales.append(DocumentLocale(lang='fr', title='Ressaut'))
    session.add(image)
    session.flush()
    create_new_version(image, author_id)
    return image


@pytest.fixture
def docs(session, user_ids) -> Docs:
    contributor_id = user_ids['contributor']
    return Docs(
        collaborative=_image(session, contributor_id, 'collab.jpg', 'collaborative'),
        personal=_image(session, contributor_id, 'personal.jpg', 'personal'),
        svg=_image(session, contributor_id, 'drawing.svg', 'personal'),
    )


def _backend(filename='rotated.jpg', status_code=200):
    return Mock(status_code=status_code, json=Mock(return_value={'filename': filename}))


def _rotate(client, image, username, status, rotation=None):
    body = {'document_id': image.document_id}
    if rotation is not None:
        body['rotation'] = rotation
    return send_json(
        client, 'post', URL, body, headers=auth_headers(username), status=status
    )


def test_moderator_rotates_a_collaborative_image(client, session, docs, user_ids):
    with patch(BACKEND, return_value=_backend()) as backend:
        response = _rotate(client, docs.collaborative, 'moderator', 200, rotation=-90)

    assert response.json == {'filename': 'rotated.jpg'}
    assert backend.call_args.kwargs['data']['filename'] == 'collab.jpg'
    assert backend.call_args.kwargs['data']['rotation'] == '-90'
    session.expire_all()
    assert session.get(Image, docs.collaborative.document_id).filename == 'rotated.jpg'
    # the old version keeps the old file
    filenames = (
        session.query(ArchiveImage.filename)
        .filter(ArchiveImage.document_id == docs.collaborative.document_id)
        .order_by(ArchiveImage.id)
        .all()
    )
    assert [f for (f,) in filenames] == ['collab.jpg', 'rotated.jpg']
    last = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == docs.collaborative.document_id)
        .order_by(DocumentVersion.id.desc())
        .first()
    )
    assert last.history_metadata.comment == 'Rotated image'
    assert last.history_metadata.user_id == user_ids['moderator']


def test_author_rotates_a_personal_image(client, session, docs):
    with patch(BACKEND, return_value=_backend()) as backend:
        _rotate(client, docs.personal, 'contributor', 200)

    # a quarter turn clockwise by default
    assert backend.call_args.kwargs['data']['rotation'] == '90'
    session.expire_all()
    assert session.get(Image, docs.personal.document_id).filename == 'rotated.jpg'


def test_author_cannot_rotate_a_collaborative_image(client, docs):
    with patch(BACKEND) as backend:
        _rotate(client, docs.collaborative, 'contributor', 403)
    backend.assert_not_called()


def test_other_user_cannot_rotate_a_personal_image(client, docs):
    with patch(BACKEND) as backend:
        _rotate(client, docs.personal, 'contributor2', 403)
    backend.assert_not_called()


def test_anonymous_cannot_rotate(client, docs):
    body = {'document_id': docs.personal.document_id}
    send_json(client, 'post', URL, body, status=403)


def test_svg_cannot_be_rotated(client, docs):
    with patch(BACKEND) as backend:
        _rotate(client, docs.svg, 'moderator', 400)
    backend.assert_not_called()


def test_rotation_is_a_quarter_or_half_turn(client, docs):
    with patch(BACKEND) as backend:
        _rotate(client, docs.personal, 'moderator', 422, rotation=45)
    backend.assert_not_called()


def test_unknown_image(client, docs):
    body = {'document_id': 9999999}
    headers = auth_headers('moderator')
    send_json(client, 'post', URL, body, headers=headers, status=400)


def test_backend_error_keeps_the_image(client, session, docs):
    with patch(BACKEND, return_value=_backend(status_code=500)):
        _rotate(client, docs.collaborative, 'moderator', 500)
    session.expire_all()
    assert session.get(Image, docs.collaborative.document_id).filename == 'collab.jpg'
