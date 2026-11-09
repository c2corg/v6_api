import datetime
from dataclasses import dataclass
from unittest.mock import call, patch

import pytest
from pydiscourse.exceptions import DiscourseClientError
from requests import Response
from requests.exceptions import ConnectionError

from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.common.document_types import OUTING_TYPE
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.security.discourse_client import (
    DisabledDiscourseClient,
    set_discourse_client,
)
from c2corg_api.tests import auth_headers, post_json_with_contributor, send_json
from c2corg_api.views.document import create_new_version
from c2corg_api.views.forum import TITLE_MAX_LENGTH, topic_title


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
    create_new_version(waypoint_with_topic, user_ids['contributor'])
    update_feed_document_create(waypoint_with_topic, user_ids['contributor'])

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
        title=f'{locale.document_id}_{locale.lang} · Image',
        category_id='Commentaires',
    )


@patch('pydiscourse.client.DiscourseClient.create_post')
def test_post_title_refused(create_post_mock, client, session, docs):
    """Fall back on the id alone when Discourse refuses the title."""
    response = Response()
    response.status_code = 422
    create_post_mock.side_effect = [
        DiscourseClientError('Title seems unclear', response=response),
        {'topic_id': 10},
    ]
    locale = docs.locale_en
    post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'en'},
        status=200,
    )
    titles = [c.kwargs['title'] for c in create_post_mock.call_args_list]
    assert titles == [
        f'{locale.document_id}_en · Summit · Mont Granier',
        f'{locale.document_id}_en',
    ]
    session.expire(locale)
    assert 10 == locale.topic_id


@patch('pydiscourse.client.DiscourseClient.create_post')
def test_post_discourse_client_error(create_post_mock, client, docs):
    """Only a refused title (422) is retried, not any client error."""
    response = Response()
    response.status_code = 403
    create_post_mock.side_effect = DiscourseClientError('Forbidden', response=response)
    post_json_with_contributor(
        client,
        '/forum/topics',
        {'document_id': docs.waypoint.document_id, 'lang': 'en'},
        status=500,
    )
    assert create_post_mock.call_count == 1


def test_topic_title_outing():
    outing = Outing(document_id=1966268, date_start=datetime.date(2026, 11, 2))
    locale = OutingLocale(
        document_id=1966268, lang='fr', title='Mont Blanc par les Grands Mulets'
    )
    assert (
        topic_title(outing, locale)
        == '1966268_fr · Sortie · Mont Blanc par les Grands Mulets · 2026-11-02'
    )


def test_topic_title_route():
    route = Route(document_id=56789)
    locale = RouteLocale(
        document_id=56789,
        lang='fr',
        title='Voie des Cristalliers',
        title_prefix='Mont Blanc',
    )
    assert (
        topic_title(route, locale)
        == '56789_fr · Itinéraire · Mont Blanc : Voie des Cristalliers'
    )


def test_topic_title_waypoint_type():
    """A waypoint is named by its type, unless the type says nothing."""
    hut = Waypoint(document_id=123, waypoint_type='hut')
    locale = WaypointLocale(document_id=123, lang='de', title='Goûterhütte')
    assert topic_title(hut, locale) == '123_de · Hütte · Goûterhütte'

    misc = Waypoint(document_id=124, waypoint_type='misc')
    locale = WaypointLocale(document_id=124, lang='fr', title='Pierre plate')
    assert topic_title(misc, locale) == '124_fr · Point de passage · Pierre plate'


def test_topic_title_xreport():
    xreport = Xreport(document_id=1965903, date=datetime.date(2026, 8, 14))
    locale = XreportLocale(document_id=1965903, lang='en', title='Crevasse fall')
    assert (
        topic_title(xreport, locale)
        == '1965903_en · Incident / accident · Crevasse fall · 2026-08-14'
    )


def test_topic_title_shouting():
    route = Route(document_id=1)
    locale = RouteLocale(
        document_id=1, lang='fr', title='VOIE NORMALE', title_prefix='MONT BLANC'
    )
    assert topic_title(route, locale) == '1_fr · Itinéraire · Mont blanc : Voie normale'


def test_topic_title_too_long():
    """Only the title of the document is shortened."""
    outing = Outing(document_id=1966268, date_start=datetime.date(2026, 11, 2))
    locale = OutingLocale(document_id=1966268, lang='fr', title='x' * 300)
    title = topic_title(outing, locale)
    assert len(title) == TITLE_MAX_LENGTH
    assert title.startswith('1966268_fr · Sortie · xxx')
    assert title.endswith('x… · 2026-11-02')


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


def _put_as_moderator(client, url, document):
    """PUT a document update as the moderator."""
    body = {'message': 'Update', 'document': document}
    headers = auth_headers(username='moderator')
    return send_json(client, 'put', url, body, headers=headers, status=200)


@pytest.fixture
def update_topic():
    """Mock the renaming of the topics in Discourse, run as soon as committed."""
    with (
        patch('c2corg_api.views.forum.in_background', side_effect=lambda op: op()),
        patch('pydiscourse.client.DiscourseClient.update_topic') as update_topic,
    ):
        yield update_topic


def test_put_renames_topic(client, docs, update_topic):
    """The topic follows the title and the type of the document."""
    waypoint = docs.waypoint_with_topic
    locale = docs.locale_en_with_topic
    _put_as_moderator(
        client,
        f'/waypoints/{waypoint.document_id}',
        {
            'document_id': waypoint.document_id,
            'version': waypoint.version,
            'waypoint_type': 'lake',
            'elevation': 2203,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Granier lake',
                    'description': '...',
                    'version': locale.version,
                }
            ],
        },
    )
    update_topic.assert_called_once_with(
        '/t/-/1.json', title=f'{waypoint.document_id}_en · Lake · Granier lake'
    )


def test_put_keeps_topic(client, docs, update_topic):
    """An update that leaves the title as it is does not call the forum."""
    waypoint = docs.waypoint_with_topic
    locale = docs.locale_en_with_topic
    _put_as_moderator(
        client,
        f'/waypoints/{waypoint.document_id}',
        {
            'document_id': waypoint.document_id,
            'version': waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 2500,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': 'another description',
                    'version': locale.version,
                }
            ],
        },
    )
    update_topic.assert_not_called()


def test_put_renames_route_topic(client, session, user_ids, docs, update_topic):
    """A new main waypoint changes the title prefix of the route, and the topic."""
    route = Route(activities=['skitouring'], elevation_max=2203)
    route.locales.append(
        RouteLocale(
            lang='en', title='North face', document_topic=DocumentTopic(topic_id=2)
        )
    )
    session.add(route)
    session.flush()
    create_new_version(route, user_ids['contributor'])
    update_feed_document_create(route, user_ids['contributor'])
    _put_as_moderator(
        client,
        f'/routes/{route.document_id}',
        {
            'document_id': route.document_id,
            'version': route.version,
            'activities': ['skitouring'],
            'elevation_max': 2203,
            'main_waypoint_id': docs.waypoint.document_id,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'North face',
                    'version': route.locales[0].version,
                }
            ],
            'associations': {'waypoints': [{'document_id': docs.waypoint.document_id}]},
        },
    )
    update_topic.assert_called_once_with(
        '/t/-/2.json',
        title=f'{route.document_id}_en · Route · Mont Granier : North face',
    )


def test_put_rename_failure(client, docs, update_topic):
    """The edit is saved even when the forum cannot rename the topic."""
    update_topic.side_effect = ConnectionError()
    waypoint = docs.waypoint_with_topic
    locale = docs.locale_en_with_topic
    _put_as_moderator(
        client,
        f'/waypoints/{waypoint.document_id}',
        {
            'document_id': waypoint.document_id,
            'version': waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 2203,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Granier',
                    'description': '...',
                    'version': locale.version,
                }
            ],
        },
    )
    assert update_topic.call_count == 1
