import datetime
from dataclasses import dataclass
from unittest.mock import call, patch

import pytest
from requests.exceptions import ConnectionError

from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.common.document_types import OUTING_TYPE
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.discourse_client import (
    DisabledDiscourseClient,
    set_discourse_client,
)
from c2corg_api.tests import post_json_with_contributor


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint: Waypoint
    locale_en: WaypointLocale
    waypoint_with_topic: Waypoint
    locale_en_with_topic: WaypointLocale
    image: Image
    image_locale_en: DocumentLocale
    outing: Outing


@pytest.fixture
def docs(session, user_ids) -> Docs:
    waypoint = Waypoint(waypoint_type='summit', elevation=2203)
    locale_en = WaypointLocale(
        lang='en', title='Mont Granier', description='...', access='yep'
    )
    waypoint.locales.append(locale_en)
    waypoint.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
    session.add(waypoint)

    waypoint_with_topic = Waypoint(waypoint_type='summit', elevation=2203)
    document_topic = DocumentTopic(topic_id=1)
    locale_en_with_topic = WaypointLocale(
        lang='en',
        title='Mont Granier',
        description='...',
        access='yep',
        document_topic=document_topic,
    )
    waypoint_with_topic.locales.append(locale_en_with_topic)
    waypoint_with_topic.geometry = DocumentGeometry(
        geom='SRID=3857;POINT(635956 5723604)'
    )
    session.add(waypoint_with_topic)

    image = Image(
        filename='image.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )
    image_locale_en = DocumentLocale(lang='en', title='', description='')
    image.locales.append(image_locale_en)
    image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
    session.add(image)

    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        locales=[OutingLocale(lang='en', title='Mont Granier / skitouring')],
    )
    session.add(outing)
    session.flush()

    for user_id in (
        user_ids['contributor'],
        user_ids['contributor2'],
    ):
        session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=outing.document_id,
                child_document_type=OUTING_TYPE,
            )
        )

    session.flush()
    return Docs(
        waypoint=waypoint,
        locale_en=locale_en,
        waypoint_with_topic=waypoint_with_topic,
        locale_en_with_topic=locale_en_with_topic,
        image=image,
        image_locale_en=image_locale_en,
        outing=outing,
    )


def test_post_document_not_exists(client, docs):
    json = post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'fr'},
        status=400,
    )
    errors = json.get('errors')
    assert 'Document not found' == errors[0].get('description')


def test_post_topic_exists(client, docs):
    json = post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint_with_topic.document_id, 'lang': 'en'},
        status=400,
    )
    errors = json.get('errors')
    assert 'Topic already exists' == errors[0].get('description')
    assert 1 == errors[0].get('topic_id')


def test_post_forum_disabled(client, session, docs):
    """Refuse to create a topic when the API runs without a forum."""
    set_discourse_client(DisabledDiscourseClient())
    json = post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'en'},
        status=503,
    )
    assert 'The forum is disabled' == json['errors'][0]['description']
    session.expire(docs.locale_en)
    assert docs.locale_en.topic_id is None


@patch('pydiscourse.client.DiscourseClient.create_post', side_effect=ConnectionError())
def test_post_discourse_down(create_post_mock, client, docs):
    post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'en'},
        status=500,
    )


@patch('pydiscourse.client.DiscourseClient.create_post', return_value={'topic_id': 10})
def test_post_success(create_post_mock, client, session, docs):
    version = docs.locale_en.version
    json = post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'en'},
        status=200,
    )
    session.expire(docs.locale_en)
    assert 10 == docs.locale_en.topic_id
    assert version == docs.locale_en.version
    assert 10 == json.get('topic_id')

    cache_version = session.get(CacheVersion, docs.waypoint.document_id)
    assert cache_version.version == 2


@patch('pydiscourse.client.DiscourseClient.create_post', return_value={'topic_id': 10})
def test_post_without_title(create_post_mock, client, docs):
    """Test topic link content for documents without title"""
    locale = docs.image_locale_en
    referer = f'https://www.camptocamp.org/images/{locale.document_id}/{locale.lang}'
    post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.image.document_id, 'lang': 'en'},
        headers={'Referer': referer},
        status=200,
    )
    create_post_mock.assert_called_with(
        '<a href="{}">{}</a>'.format(
            referer, f'/images/{locale.document_id}/{locale.lang}'
        ),
        title=f'{locale.document_id}_{locale.lang}',
        category_id='Commentaires',
    )


@patch(
    'pydiscourse.client.DiscourseClient._post',
    side_effect=[{'topic_id': 10}, {}, {}],
)
def test_post_invite_participants(_post_mock, client, docs):
    """Test outing participants are invited in the topic"""
    post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.outing.document_id, 'lang': 'en'},
        status=200,
    )
    _post_mock.assert_has_calls(
        [
            call('/t/10/invite.json', user='contributor'),
            call('/t/10/invite.json', user='contributor2'),
        ],
        any_order=True,
    )
