import json
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from shapely.geometry import LineString, shape
from shapely.geometry.point import Point

from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.common.attributes import activities, quality_types
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import (
    OUTING_TYPE,
    ArchiveOuting,
    ArchiveOutingLocale,
    Outing,
    OutingLocale,
)
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import (
    assert_error,
    assert_notified_es,
    assert_required,
    auth_headers,
    errors_of,
    get_error,
    get_feed_change,
    get_locale,
    send_json,
)
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

OUTINGS = DocType('/outings', OUTING_TYPE, Outing, ArchiveOuting, ArchiveOutingLocale)


TRACK_JSON = (
    '{"type": "LineString", "coordinates": [[635956, 5723604], [635966, 5723644]]}'
)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    outing: Outing
    locale_en: OutingLocale
    locale_fr: OutingLocale
    outing_version: object
    outing2: Outing
    outing3: Outing
    outing4: Outing
    waypoint: Waypoint
    image: Image
    article1: Article
    route: Route


@pytest.fixture
def docs(session, user_ids) -> Docs:
    outing = Outing(
        activities=['skitouring'],
        date_start=date(2016, 1, 1),
        date_end=date(2016, 1, 1),
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        elevation_access=900,
        condition_rating='good',
    )
    locale_en = OutingLocale(
        lang='en',
        title='Mont Blanc from the air',
        description='...',
        weather='sunny',
        document_topic=DocumentTopic(topic_id=1),
    )

    locale_fr = OutingLocale(
        lang='fr',
        title='Mont Blanc du ciel',
        description='...',
        weather='grand beau',
    )

    outing.locales.append(locale_en)
    outing.locales.append(locale_fr)

    outing.geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )

    session.add(outing)
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(outing, user_id)
    outing_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == outing.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )
    update_feed_document_create(outing, user_id)

    outing2 = Outing(
        activities=['skitouring'],
        date_start=date(2016, 2, 1),
        date_end=date(2016, 2, 1),
        height_diff_up=600,
        elevation_max=1800,
        elevation_access=700,
        condition_rating='average',
        locales=[
            OutingLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                weather='sunny',
            )
        ],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(0 0)'),
    )
    session.add(outing2)
    session.flush()
    create_new_version(outing2, user_id)

    outing3 = Outing(
        activities=['skitouring'],
        date_start=date(2016, 2, 1),
        date_end=date(2016, 2, 2),
        height_diff_up=200,
        elevation_max=1200,
        elevation_access=800,
        condition_rating='poor',
    )
    session.add(outing3)
    outing4 = Outing(
        activities=['skitouring'],
        date_start=date(2016, 2, 1),
        date_end=date(2016, 2, 3),
        height_diff_up=500,
        elevation_max=1400,
        elevation_access=800,
        condition_rating='excellent',
    )
    outing4.locales.append(
        OutingLocale(lang='en', title='Mont Granier (en)', description='...')
    )
    outing4.locales.append(
        OutingLocale(lang='fr', title='Mont Granier (fr)', description='...')
    )
    session.add(outing4)

    waypoint = Waypoint(
        waypoint_type='summit',
        elevation=4,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    waypoint.locales.append(
        WaypointLocale(
            lang='en', title='Mont Granier (en)', description='...', access='yep'
        )
    )
    waypoint.locales.append(
        WaypointLocale(
            lang='fr', title='Mont Granier (fr)', description='...', access='ouai'
        )
    )
    session.add(waypoint)

    image = Image(
        filename='20160101-00:00:00.jpg',
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    image.locales.append(DocumentLocale(lang='en', title='...'))
    session.add(image)

    article1 = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article1)
    session.flush()

    # add some associations
    route = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        ),
    )
    route.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            gear='paraglider',
            title_prefix='Main waypoint title',
        )
    )
    route.locales.append(
        RouteLocale(
            lang='fr',
            title='Mont Blanc du ciel',
            description='...',
            gear='paraglider',
        )
    )
    session.add(route)
    session.flush()

    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint, child_document=route),
        user_id=user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=route, child_document=outing),
        user_id=user_id,
    )

    scenarios.add_association(
        session,
        Association(
            parent_document_id=user_id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing.document_id,
            child_document_type=OUTING_TYPE,
        ),
        user_id=user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=outing, child_document=image),
        user_id=user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=outing, child_document=article1),
        user_id=user_id,
    )
    session.flush()
    return Docs(
        outing=outing,
        locale_en=locale_en,
        locale_fr=locale_fr,
        outing_version=outing_version,
        outing2=outing2,
        outing3=outing3,
        outing4=outing4,
        waypoint=waypoint,
        image=image,
        article1=article1,
        route=route,
    )


def test_get_collection(client, session, user_ids, docs):
    body = scenarios.get_collection(client, session, OUTINGS)
    assert len(body['documents']) == 4
    doc1 = body['documents'][0]
    assert 'frequentation' not in doc1
    assert 'condition_rating' in doc1

    doc4 = body['documents'][3]
    assert 'author' in doc4
    author = doc4['author']
    assert 'username' not in author
    assert author['name'] == 'Contributor'
    assert author['user_id'] == user_ids['contributor']

    for doc in body['documents']:
        # number of associated images
        assert 'img_count' in doc
        assert doc['img_count'] == (
            1 if doc['document_id'] == docs.outing.document_id else 0
        )


def test_get_collection_for_route(client, session, docs):
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?r=' + str(docs.route.document_id), status=200
    )
    documents = response.json['documents']
    assert documents[0]['document_id'] == docs.outing.document_id
    assert response.json['total'] == 1


def test_get_collection_has_geom(client, session, docs):
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?r=' + str(docs.route.document_id), status=200
    )
    documents = response.json['documents']
    assert documents[0]['geometry']['has_geom_detail'] is True


def test_get_collection_for_waypoint(client, session, docs):
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?w=' + str(docs.waypoint.document_id), status=200
    )

    documents = response.json['documents']

    assert documents[0]['document_id'] == docs.outing.document_id
    assert response.json['total'] == 1


def test_get_collection_for_user(client, session, user_ids, docs):
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?u=' + str(user_ids['contributor']), status=200
    )

    documents = response.json['documents']

    assert documents[0]['document_id'] == docs.outing.document_id
    assert response.json['total'] == 1


def test_get_collection_paginated(client, session, docs):
    client.get('/outings?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, OUTINGS, {'offset': 0, 'limit': 0}),
        [],
        4,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, OUTINGS, {'offset': 0, 'limit': 1}),
        [docs.outing4.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, OUTINGS, {'offset': 0, 'limit': 2}),
        [docs.outing4.document_id, docs.outing3.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, OUTINGS, {'offset': 1, 'limit': 2}),
        [docs.outing3.document_id, docs.outing2.document_id],
        4,
    )


def test_get_collection_lang(client, docs):
    scenarios.get_collection_lang(client, OUTINGS)


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, OUTINGS, {'act': 'skitouring'}),
        [
            docs.outing4.document_id,
            docs.outing3.document_id,
            docs.outing2.document_id,
            docs.outing.document_id,
        ],
        4,
    )

    body = scenarios.get_collection_search(
        client, OUTINGS, {'act': 'skitouring', 'limit': 2}
    )
    assert body.get('total') == 4
    assert len(body.get('documents')) == 2

    body = scenarios.get_collection_search(
        client, OUTINGS, {'date': '2015-12-31,2016-01-02'}
    )
    assert body.get('total') == 1


def test_get(client, user_ids, docs):
    body = scenarios.get(client, OUTINGS, docs.outing, title=docs.locale_en.title)
    assert body.get('activities') == docs.outing.activities
    _assert_geometry(body)
    assert 'frequentation' in body
    assert body['license']['id'] == 'CC-BY-NC-ND-3.0'
    assert 'maps' not in body

    assert 'associations' in body
    associations = body.get('associations')
    assert 'waypoints' not in associations
    assert 'routes' in associations
    assert 'xreports' in associations
    assert 'images' in associations
    assert 'users' in associations
    assert 'articles' in associations

    linked_articles = associations.get('articles')
    assert len(linked_articles) == 1
    assert docs.article1.document_id == linked_articles[0].get('document_id')

    linked_routes = associations.get('routes')
    assert len(linked_routes) == 1
    assert docs.route.document_id == linked_routes[0].get('document_id')

    linked_users = associations.get('users')
    assert len(linked_users) == 1
    # TODO id -> document_id
    assert linked_users[0]['document_id'] == user_ids['contributor']

    linked_images = associations.get('images')
    assert len(linked_images) == 1
    assert linked_images[0]['document_id'] == docs.image.document_id
    assert 'geometry' in linked_images[0]
    assert 'geom' in linked_images[0].get('geometry')

    locale_en = get_locale(body.get('locales'), 'en')
    assert 1 == locale_en.get('topic_id')


def test_get_edit(client, docs):
    response = client.get(
        OUTINGS.prefix + '/' + str(docs.outing.document_id) + '?e=1', status=200
    )
    body = response.json

    assert 'maps' not in body
    assert 'areas' not in body
    assert 'associations' in body
    associations = body['associations']
    assert 'waypoints' not in associations
    assert 'routes' in associations
    assert 'users' in associations
    assert 'images' not in associations


def test_get_version(client, docs):
    scenarios.get_version(client, OUTINGS, docs.outing, docs.outing_version)


def test_get_sort_asc(client, session, docs):
    """Test ascending sorting of results for height_diff_up keyword."""
    reset_search_index(session)
    response = client.get(OUTINGS.prefix + '?sort=height_diff_up', status=200)
    response_ids = [d['document_id'] for d in response.json['documents']]
    outing_ids = [
        d.document_id for d in [docs.outing3, docs.outing4, docs.outing2, docs.outing]
    ]
    assert response_ids == outing_ids


def test_get_sort_desc(client, session, docs):
    """Test descending sorting of results for elevation max keyword."""
    reset_search_index(session)
    response = client.get(OUTINGS.prefix + '?sort=-elevation_max', status=200)
    response_ids = [d['document_id'] for d in response.json['documents']]
    outing_ids = [
        d.document_id for d in [docs.outing2, docs.outing, docs.outing4, docs.outing3]
    ]
    assert response_ids == outing_ids


def test_get_sort_multi(client, session, docs):
    """Test multi-criteria sorting (elevation_max: desc,
    height_diff_up: asc)"""
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?sort=-elevation_max,height_diff_up', status=200
    )
    response_ids = [d['document_id'] for d in response.json['documents']]
    outing_ids = [
        d.document_id for d in [docs.outing2, docs.outing, docs.outing4, docs.outing3]
    ]
    assert response_ids == outing_ids


def test_get_sort_numeric_enum(client, session, docs):
    """Test sorting with two different criteria:
    numeric (elevation_access) and enum (condition_rating)"""
    reset_search_index(session)
    response = client.get(
        OUTINGS.prefix + '?sort=-elevation_access,condition_rating', status=200
    )
    response_ids = [d['document_id'] for d in response.json['documents']]
    outing_ids = [
        d.document_id for d in [docs.outing, docs.outing4, docs.outing3, docs.outing2]
    ]
    assert response_ids == outing_ids


def test_get_sort_error(client, session, docs):
    """Test failure of request (status 500) if an unknown
    keyword is used.
    """
    reset_search_index(session)
    client.get(OUTINGS.prefix + '?sort=-elevation_axess', status=500)


def test_get_version_without_activity(client, session, docs):
    """Tests that old outings versions without activity include the fields
    of all activities.
    """
    docs.outing_version.document_archive.activities = []
    session.flush()
    body = scenarios.get_version(client, OUTINGS, docs.outing, docs.outing_version)
    locale = body['document']['locales'][0]
    assert 'title' in locale


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, OUTINGS, docs.outing)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, OUTINGS, docs.outing)


def test_get_lang(client, docs):
    scenarios.get_lang(client, OUTINGS, docs.outing)


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, OUTINGS, docs.outing)


def test_get_404(client, docs):
    scenarios.get_404(client, OUTINGS)


def test_get_caching(client, docs):
    scenarios.get_caching(client, OUTINGS, docs.outing)


def test_get_info(client, docs):
    body, locale = scenarios.get_info(client, OUTINGS, docs.outing, 'en')
    assert locale.get('lang') == 'en'


def test_get_info_best_lang(client, docs):
    body, locale = scenarios.get_info(client, OUTINGS, docs.outing, 'es')
    assert locale.get('lang') == 'fr'


def test_get_info_404(client, docs):
    scenarios.get_info_404(client, OUTINGS)


def test_post_error(client, docs):
    # an invalid body: its errors alone, the rules of the API (the
    # associations) need a valid body (see test_post_missing_route_user_id)
    body = scenarios.post_error(client, OUTINGS, {}, status=422)
    errors = errors_of(body)
    assert len(errors) == 3
    assert_required(get_error(errors, 'activities'), 'activities')
    assert_required(get_error(errors, 'date_end'), 'date_end')
    assert_required(get_error(errors, 'date_start'), 'date_start')


def test_post_empty_activities_error(client, user_ids, docs):
    body = scenarios.post_error(
        client,
        OUTINGS,
        {
            'activities': [],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'associations': {
                'routes': [{'document_id': docs.route.document_id}],
                'users': [{'document_id': user_ids['contributor']}],
            },
        },
        status=422,
    )
    errors = errors_of(body)
    assert len(errors) == 1
    error = get_error(errors, 'activities')
    assert error.get('description') == 'Shorter than minimum length 1'


def test_post_invalid_activity(client, user_ids, docs):
    body_post = {
        'activities': ['cooking'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        'associations': {
            'routes': [{'document_id': docs.route.document_id}],
            'users': [{'document_id': user_ids['contributor']}],
        },
    }
    body = scenarios.post_error(client, OUTINGS, body_post, status=422)
    # the schema rejects the body, so the association checks also miss
    # their data and add their own errors
    assert_error(
        errors_of(body),
        'activities.0',
        f'"cooking" is not one of {", ".join(activities)}',
    )


def test_post_missing_title(client, user_ids, docs):
    body_post = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en'}],
        'associations': {
            'routes': [{'document_id': docs.route.document_id}],
            'users': [{'document_id': user_ids['contributor']}],
        },
    }
    body = scenarios.post_missing_title(client, OUTINGS, body_post)
    errors = errors_of(body)
    assert len(errors) == 1


def test_post_date_start_is_tomorrow(client, user_ids, docs):
    later = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
    body_post = {
        'activities': ['skitouring'],
        'date_start': later,
        'date_end': '2016-01-01',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'users': [
                {'document_id': user_ids['contributor']},
                {'document_id': user_ids['contributor2']},
            ],
            'routes': [{'document_id': docs.route.document_id}],
            # images are ignored
            'images': [{'document_id': docs.route.document_id}],
        },
    }
    body = scenarios.post_error(client, OUTINGS, body_post)
    errors = body.get('errors')
    assert len(errors) == 1
    assert errors[0]['name'] == 'date_start'
    assert errors[0]['description'] == 'can not be sometime in the future'


def test_post_date_end_is_tomorrow(client, user_ids, docs):
    later = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
    body_post = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': later,
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'users': [
                {'document_id': user_ids['contributor']},
                {'document_id': user_ids['contributor2']},
            ],
            'routes': [{'document_id': docs.route.document_id}],
            # images are ignored
            'images': [{'document_id': docs.route.document_id}],
        },
    }
    body = scenarios.post_error(client, OUTINGS, body_post)
    errors = body.get('errors')
    assert len(errors) == 1
    assert errors[0]['name'] == 'date_end'
    assert errors[0]['description'] == 'can not be sometime in the future'


def test_post_end_date_is_prior_start_date(client, user_ids, docs):
    today = date.today()
    yesterday = today - timedelta(days=1)
    body_post = {
        'activities': ['skitouring'],
        'date_start': today.strftime('%Y-%m-%d'),
        'date_end': yesterday.strftime('%Y-%m-%d'),
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'users': [
                {'document_id': user_ids['contributor']},
                {'document_id': user_ids['contributor2']},
            ],
            'routes': [{'document_id': docs.route.document_id}],
            # images are ignored
            'images': [{'document_id': docs.route.document_id}],
        },
    }
    body = scenarios.post_error(client, OUTINGS, body_post)
    errors = body.get('errors')
    assert len(errors) == 1
    assert errors[0]['name'] == 'date_end'
    assert errors[0]['description'] == 'can not be prior the starting date'


def test_post_non_whitelisted_attribute(client, session, user_ids, docs):
    body = {
        'activities': ['skitouring'],
        'protected': True,
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'routes': [{'document_id': docs.route.document_id}],
            'users': [{'document_id': user_ids['contributor']}],
        },
    }
    scenarios.post_non_whitelisted_attribute(client, session, OUTINGS, body)


def test_post_missing_content_type(client, docs):
    scenarios.post_missing_content_type(client, OUTINGS, {})


def test_post_missing_route_user_id(client, docs):
    request_body = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            # missing route_id,
            'users': []
        },
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client, 'post', OUTINGS.prefix, request_body, headers=headers, status=400
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 2
    assert_error(errors, 'associations.users', 'at least one user required')
    assert_error(errors, 'associations.routes', 'at least one route required')


def test_post_invalid_route_id(client, docs):
    request_body = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'routes': [{'document_id': docs.waypoint.document_id}],
            'users': [{'document_id': -999}],
        },
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client, 'post', OUTINGS.prefix, request_body, headers=headers, status=400
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 4

    assert_error(
        errors,
        'associations.routes',
        'document "' + str(docs.waypoint.document_id) + '" is not of type "r"',
    )
    assert_error(
        errors,
        'associations.users',
        'document "-999" does not exist or is redirected',
    )
    assert_error(errors, 'associations.users', 'at least one user required')
    assert_error(errors, 'associations.routes', 'at least one route required')


def test_post_success(client, session, user_ids, docs):
    body = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'users': [
                {'document_id': user_ids['contributor']},
                {'document_id': user_ids['contributor2']},
            ],
            'routes': [{'document_id': docs.route.document_id}],
            # images are ignored
            'images': [{'document_id': docs.route.document_id}],
        },
    }
    body, doc = scenarios.post_success(client, session, OUTINGS, body)
    _assert_geometry(body)
    _assert_default_geometry(body)
    assert doc.date_start == date(2016, 1, 1)
    assert doc.date_end == date(2016, 1, 2)

    version = doc.versions[0]

    archive_outing = version.document_archive
    assert archive_outing.activities == ['skitouring']
    assert archive_outing.elevation_max == 1500

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == 'Some nice loop'

    archive_geometry = version.document_geometry_archive
    assert archive_geometry.version == doc.geometry.version
    assert archive_geometry.geom_detail is not None

    association_route = session.get(
        Association, (docs.route.document_id, doc.document_id)
    )
    assert association_route is not None

    association_route_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == docs.route.document_id)
        .filter(AssociationLog.child_document_id == doc.document_id)
        .first()
    )
    assert association_route_log is not None

    association_user = session.get(
        Association, (user_ids['contributor'], doc.document_id)
    )
    assert association_user is not None

    association_user2 = session.get(
        Association, (user_ids['contributor2'], doc.document_id)
    )
    assert association_user2 is not None

    association_user_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == user_ids['contributor'])
        .filter(AssociationLog.child_document_id == doc.document_id)
        .first()
    )
    assert association_user_log is not None

    # check that a change is created in the feed
    feed_change = get_feed_change(session, doc.document_id)
    assert feed_change is not None
    assert feed_change.activities == ['skitouring']
    assert feed_change.user_ids == [
        user_ids['contributor'],
        user_ids['contributor2'],
    ]
    assert feed_change.area_ids == []


def test_post_set_default_geom_from_route(client, session, user_ids, docs):
    body = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-02',
        'elevation_min': 700,
        'elevation_max': 1500,
        'height_diff_up': 800,
        'height_diff_down': 800,
        'locales': [{'lang': 'en', 'title': 'Some nice loop', 'weather': 'sunny'}],
        'associations': {
            'users': [{'document_id': user_ids['contributor']}],
            'routes': [{'document_id': docs.route.document_id}],
        },
    }
    body, doc = scenarios.post_success(client, session, OUTINGS, body)
    _assert_default_geometry(body, x=635961, y=5723624)


def test_put_wrong_document_id(client, user_ids, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.outing.version,
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        }
    }
    scenarios.put_wrong_document_id(client, OUTINGS, body, user='moderator')


def test_put_wrong_document_version(client, user_ids, docs):
    body = {
        'document': {
            'document_id': docs.outing.document_id,
            'version': -9999,
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        }
    }
    scenarios.put_wrong_version(
        client, OUTINGS, body, docs.outing.document_id, user='moderator'
    )


def test_put_wrong_locale_version(client, user_ids, docs):
    body = {
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': -9999,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        }
    }
    scenarios.put_wrong_version(
        client, OUTINGS, body, docs.outing.document_id, user='moderator'
    )


def test_put_wrong_ids(client, user_ids, docs):
    body = {
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        }
    }
    scenarios.put_wrong_ids(
        client, OUTINGS, body, docs.outing.document_id, user='moderator'
    )


def test_put_no_document(client, docs):
    scenarios.put_no_document(client, OUTINGS, docs.outing.document_id)


def test_put_wrong_user(client, user_ids, docs):
    """Test that a non-moderator user who is not associated to the outing
    is not allowed to modify.
    """
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    headers = auth_headers(username='contributor2')
    send_json(
        client,
        'put',
        OUTINGS.prefix + '/' + str(docs.outing.document_id),
        body,
        headers=headers,
        status=403,
    )


def test_put_good_user(client, user_ids, docs):
    """Test that a non-moderator user who is associated to the outing
    is allowed to modify.
    """
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'put',
        OUTINGS.prefix + '/' + str(docs.outing.document_id),
        body,
        headers=headers,
        status=200,
    )


def test_put_success_all(client, session, user_ids, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring', 'hiking'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': {
                'version': docs.outing.geometry.version,
                'geom_detail': '{"type": "LineString", "coordinates": '
                + '[[635956, 5723604], [635976, 5723654]]}',
            },
            'associations': {
                'users': [
                    {'document_id': user_ids['contributor']},
                    {'document_id': user_ids['contributor2']},
                ],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    (body, outing) = scenarios.put_success_all(
        client,
        session,
        OUTINGS,
        body,
        docs.outing,
        user='moderator',
        cache_version=3,
        locale_fr=docs.locale_fr,
    )

    # default geom is updated with the new track
    _assert_default_geometry(body, x=635966, y=5723629)

    assert outing.elevation_max == 1600
    locale_en = outing.get_locale('en')
    assert locale_en.description == '...'
    assert locale_en.weather == 'mostly sunny'

    # version with lang 'en'
    versions = outing.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'Mont Blanc from the air'
    assert archive_locale.weather == 'mostly sunny'

    archive_document_en = version_en.document_archive
    assert archive_document_en.activities == ['skitouring', 'hiking']
    assert archive_document_en.elevation_max == 1600

    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 2

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == 'Mont Blanc du ciel'
    assert archive_locale.weather == 'grand beau'

    # test that there are now 2 associated users
    association_user = session.get(
        Association, (user_ids['contributor'], outing.document_id)
    )
    assert association_user is not None
    association_user2 = session.get(
        Association, (user_ids['contributor2'], outing.document_id)
    )
    assert association_user2 is not None

    # check that the feed change is updated
    feed_change = get_feed_change(session, outing.document_id)
    assert feed_change is not None
    assert feed_change.activities == ['skitouring', 'hiking']
    assert feed_change.area_ids == []
    assert feed_change.user_ids == [
        user_ids['contributor'],
        user_ids['contributor2'],
    ]


def test_put_success_figures_only(client, session, user_ids, docs):
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    (body, route) = scenarios.put_success_figures_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )

    assert route.elevation_max == 1600


def test_put_update_default_geom(client, session, user_ids, docs):
    """Tests that the default geometry can be updated directly."""
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': {
                'version': docs.outing.geometry.version,
                'geom': '{"type": "Point", "coordinates": [635000, 5723000]}',
            },
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    (body, route) = scenarios.put_success_figures_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )
    _assert_default_geometry(body, x=635000, y=5723000)


def test_put_keep_moved_default_geom(client, session, user_ids, docs):
    """Tests that a moved default geometry is kept with an unchanged track."""
    body = _put_geometry_body(
        docs,
        user_ids,
        {
            'version': docs.outing.geometry.version,
            'geom_detail': TRACK_JSON,
            'geom': '{"type": "Point", "coordinates": [635000, 5723000]}',
        },
    )
    (body, outing) = scenarios.put_success_figures_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )
    _assert_default_geometry(body, x=635000, y=5723000)


def test_put_keep_default_geom_same_track(client, user_ids, docs):
    """Tests that a saved default geometry is kept when saving again."""
    headers = auth_headers(username='moderator')
    url = OUTINGS.prefix + '/' + str(docs.outing.document_id)
    geom = '{"type": "Point", "coordinates": [635000, 5723000]}'

    body = _put_geometry_body(
        docs,
        user_ids,
        {
            'version': docs.outing.geometry.version,
            'geom_detail': TRACK_JSON,
            'geom': geom,
        },
    )
    send_json(client, 'put', url, body, headers=headers, status=200)

    # save again, with the geometry returned by the API
    outing = client.get(url, headers=headers, status=200).json
    body = _put_geometry_body(docs, user_ids, outing['geometry'])
    body['document']['version'] = outing['version']
    body['document']['elevation_max'] = 1700
    body['document']['locales'][0]['version'] = outing['locales'][0]['version']
    send_json(client, 'put', url, body, headers=headers, status=200)

    body = client.get(url, headers=headers, status=200).json
    assert body['elevation_max'] == 1700
    _assert_default_geometry(body, x=635000, y=5723000)


def test_put_new_track_updates_default_geom(client, session, user_ids, docs):
    """Tests that a new track moves an unchanged default geometry."""
    body = _put_geometry_body(
        docs,
        user_ids,
        {
            'version': docs.outing.geometry.version,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635976, 5723654]]}',
            'geom': '{"type": "Point", "coordinates": [635961, 5723624]}',
        },
    )
    (body, outing) = scenarios.put_success_figures_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )
    _assert_default_geometry(body, x=635966, y=5723629)


def test_put_new_track_with_moved_default_geom(client, session, user_ids, docs):
    """Tests that a moved default geometry is kept with a new track."""
    body = _put_geometry_body(
        docs,
        user_ids,
        {
            'version': docs.outing.geometry.version,
            'geom_detail': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635976, 5723654]]}',
            'geom': '{"type": "Point", "coordinates": [635000, 5723000]}',
        },
    )
    (body, outing) = scenarios.put_success_figures_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )
    _assert_default_geometry(body, x=635000, y=5723000)


def _put_geometry_body(docs, user_ids, geometry):
    return {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1600,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': geometry,
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }


def test_put_success_lang_only(client, session, user_ids, docs):
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'elevation_access': 900,
            'condition_rating': 'good',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'mostly sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    (body, route) = scenarios.put_success_lang_only(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )

    assert route.get_locale('en').weather == 'mostly sunny'


def test_put_success_new_lang(client, session, user_ids, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'elevation_access': 900,
            'condition_rating': 'good',
            'locales': [
                {
                    'lang': 'es',
                    'title': 'Mont Blanc del cielo',
                    'description': '...',
                    'weather': 'soleado',
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }
    (body, route) = scenarios.put_success_new_lang(
        client, session, OUTINGS, body, docs.outing, user='moderator'
    )

    assert route.get_locale('es').weather == 'soleado'


def test_put_success_association_update(client, session, user_ids, queue_config, docs):
    """Test updating a document by updating associations."""
    request_body = {
        'message': 'Changing associations',
        'document': {
            'document_id': docs.outing.document_id,
            'version': docs.outing.version,
            'quality': quality_types[1],
            'activities': ['skitouring'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-01',
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'elevation_access': 900,
            'condition_rating': 'good',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc from the air',
                    'description': '...',
                    'weather': 'sunny',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {
                'users': [{'document_id': user_ids['contributor2']}],
                'routes': [{'document_id': docs.route.document_id}],
            },
        },
    }

    headers = auth_headers(username='moderator')
    send_json(
        client,
        'put',
        OUTINGS.prefix + '/' + str(docs.outing.document_id),
        request_body,
        headers=headers,
        status=200,
    )

    response = client.get(
        OUTINGS.prefix + '/' + str(docs.outing.document_id),
        headers=headers,
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    document_id = body.get('document_id')
    # document version does not change!
    assert body.get('version') == docs.outing.version
    assert body.get('document_id') == document_id

    # check that the document was updated correctly
    session.expire_all()
    document = session.get(OUTINGS.model, document_id)
    assert len(document.locales) == 2

    # check that no new archive_document was created
    archive_count = (
        session.query(OUTINGS.model_archive)
        .filter(OUTINGS.model_archive.document_id == document_id)
        .count()
    )
    assert archive_count == 1

    # check that no new archive_document_locale was created
    archive_locale_count = (
        session.query(OUTINGS.model_archive_locale)
        .filter(document_id == OUTINGS.model_archive_locale.document_id)
        .count()
    )
    assert archive_locale_count == 2

    assert_notified_es(queue_config)


def test_history(client, user_ids, docs):
    id = docs.outing.document_id
    langs = ['fr', 'en']
    for lang in langs:
        body = client.get(f'/document/{id}/history/{lang}')
        username = 'contributor'
        user_id = user_ids[username]

        title = body.json['title']
        versions = body.json['versions']
        assert len(versions) == 1
        assert getattr(docs, 'locale_' + lang).title == title
        for r in versions:
            assert r['name'] == 'Contributor'
            assert 'username' not in r
            assert r['user_id'] == user_id
            assert 'written_at' in r
            assert 'version_id' in r


def test_history_no_lang(client, docs):
    id = docs.outing.document_id
    client.get(f'/document/{id}/history/es', status=404)


def test_history_no_doc(client, docs):
    client.get('/document/99999/history/es', status=404)


def test_get_associations_history(client, docs):
    logs = scenarios.get_association_logs(client, docs.outing)

    assert len(logs) == 4

    # Third association (starting from the youngest) is a user
    log = logs[2]
    parent = log['parent_document']
    assert parent['type'] == USERPROFILE_TYPE


def _assert_geometry(body):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get('geom_detail') is not None

    geom = geometry.get('geom_detail')
    line = shape(json.loads(geom))
    assert isinstance(line, LineString)
    assert line.coords[0][0] == pytest.approx(635956, abs=5e-8)
    assert line.coords[0][1] == pytest.approx(5723604, abs=5e-8)
    assert line.coords[1][0] == pytest.approx(635966, abs=5e-8)
    assert line.coords[1][1] == pytest.approx(5723644, abs=5e-8)


def _assert_default_geometry(body, x=635961, y=5723624):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get('geom') is not None

    geom = geometry.get('geom')
    point = shape(json.loads(geom))
    assert isinstance(point, Point)
    assert point.x == pytest.approx(x, abs=5e-8)
    assert point.y == pytest.approx(y, abs=5e-8)
