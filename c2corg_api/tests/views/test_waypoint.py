import datetime
import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from dogpile.cache.api import NO_VALUE
from shapely.geometry import Point, shape

from c2corg_api import caching
from c2corg_api.caching import (
    cache_document_history,
    cache_document_listing,
    cache_document_version,
)
from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion, get_cache_key
from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    DOCUMENT_TYPE,
    ArchiveDocumentGeometry,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE,
    ArchiveWaypoint,
    ArchiveWaypointLocale,
    Waypoint,
    WaypointLocale,
)
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.tests import (
    assert_error,
    assert_errors_contain,
    assert_required,
    auth_headers,
    errors_of,
    get_feed_change,
    get_locale,
    send_json,
)
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version
from c2corg_api.views.document_listings import get_documents
from c2corg_api.views.waypoint import waypoint_documents_config

WAYPOINTS = DocType(
    '/waypoints', WAYPOINT_TYPE, Waypoint, ArchiveWaypoint, ArchiveWaypointLocale
)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint: Waypoint
    locale_en: WaypointLocale
    locale_fr: WaypointLocale
    waypoint_version: DocumentVersion
    waypoint2: Waypoint
    waypoint3: Waypoint
    waypoint4: Waypoint
    waypoint5: Waypoint
    waypoint6: Waypoint
    route1: Route
    route2: Route
    route3: Route
    article1: Article
    article2: Article
    outing1: Outing
    outing2: Outing
    outing3: Outing
    topo_map1: TopoMap
    topo_map2: TopoMap
    area1: Area
    area2: Area


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    waypoint = Waypoint(waypoint_type='summit', elevation=2203)

    locale_en = WaypointLocale(
        lang='en',
        title='Mont Granier',
        description='...',
        access='yep',
        document_topic=DocumentTopic(topic_id=1),
    )

    locale_fr = WaypointLocale(
        lang='fr', title='Mont Granier', description='...', access='ouai'
    )

    waypoint.locales.append(locale_en)
    waypoint.locales.append(locale_fr)

    waypoint.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
    session.add(waypoint)
    session.flush()
    user_id = user_ids['contributor']
    create_new_version(waypoint, user_id)
    waypoint_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == waypoint.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )
    update_feed_document_create(waypoint, user_id)

    waypoint2 = Waypoint(
        waypoint_type='climbing_outdoor',
        elevation=2,
        rock_types=[],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    session.add(waypoint2)

    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=3,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    session.add(waypoint3)

    waypoint4 = Waypoint(
        waypoint_type='summit',
        elevation=4,
        protected=True,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(659775 5694854)'),
    )
    waypoint4.locales.append(
        WaypointLocale(
            lang='en',
            title='Mont Granier',
            description='...',
            access='yep',
            external_resources='https://wikipedia.com/en',
        )
    )
    waypoint4.locales.append(
        WaypointLocale(
            lang='fr',
            title='Mont Granier',
            description='...',
            access='ouai',
            external_resources='https://wikipedia.com/fr',
        )
    )
    session.add(waypoint4)

    waypoint5 = Waypoint(
        waypoint_type='summit',
        elevation=3,
        redirects_to=waypoint.document_id,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    waypoint5.locales.append(
        WaypointLocale(lang='en', title='Mont Granier', description='...', access='yep')
    )
    session.add(waypoint5)

    waypoint6 = Waypoint(
        waypoint_type='access',
        elevation=1096,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(657403 5691411)'),
    )
    waypoint6.locales.append(
        WaypointLocale(lang='fr', title='La Plagne', description='...', access='ouai')
    )
    waypoint6.locales.append(
        WaypointLocale(lang='en', title='La Plagne', description='...', access='yep')
    )
    session.add(waypoint6)
    session.flush()

    create_new_version(waypoint4, user_id)
    create_new_version(waypoint5, user_id)
    create_new_version(waypoint6, user_id)

    # add some associations
    route1_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    route1 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        main_waypoint_id=waypoint.document_id,
        geometry=route1_geometry,
    )
    route1.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
        )
    )
    session.add(route1)
    session.flush()
    route2 = Route(
        redirects_to=route1.document_id,
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        main_waypoint_id=waypoint.document_id,
    )
    route3 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
    )
    route3.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
        )
    )
    session.add(route2)
    session.add(route3)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint, child_document=waypoint4),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint, child_document=route1),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint, child_document=route2),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint4, child_document=route3),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=route1, child_document=waypoint6),
        user_id,
    )

    # article
    article1 = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article1)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=waypoint, child_document=article1),
        user_id,
    )

    article2 = Article(
        categories=['site_info'],
        activities=['hiking'],
        article_type='personal',
        locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
    )
    session.add(article2)
    session.flush()
    create_new_version(article2, user_id)

    outing1 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 3),
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )
    session.add(outing1)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=route1, child_document=outing1),
        user_id,
    )

    outing2 = Outing(
        redirects_to=outing1.document_id,
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )

    outing3 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2015, 12, 31),
        date_end=datetime.date(2016, 1, 1),
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )
    session.add(outing2)
    session.add(outing3)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=route1, child_document=outing2),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=route3, child_document=outing3),
        user_id,
    )

    # add a map
    topo_map1 = TopoMap(
        code='3232ET',
        editor='IGN',
        scale='25000',
        locales=[DocumentLocale(lang='fr', title='Belley')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
        ),
    )
    topo_map2 = TopoMap(
        code='3232ET',
        editor='IGN',
        scale='25000',
        locales=[DocumentLocale(lang='fr', title='Belley')],
    )
    session.add_all([topo_map1, topo_map2])
    session.flush()
    session.add(
        TopoMap(
            redirects_to=topo_map1.document_id,
            code='3232ET',
            editor='IGN',
            scale='25000',
            locales=[DocumentLocale(lang='fr', title='Belley')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
            ),
        )
    )
    session.add(TopoMapAssociation(document=waypoint, topo_map=topo_map2))
    session.flush()

    # add areas
    area1 = Area(
        area_type='range',
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
        ),
    )
    area2 = Area(area_type='range', locales=[DocumentLocale(lang='fr', title='France')])

    session.add_all([area1, area2])
    session.add(AreaAssociation(document=waypoint, area=area2))
    session.flush()
    return Docs(
        waypoint=waypoint,
        locale_en=locale_en,
        locale_fr=locale_fr,
        waypoint_version=waypoint_version,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        waypoint4=waypoint4,
        waypoint5=waypoint5,
        waypoint6=waypoint6,
        route1=route1,
        route2=route2,
        route3=route3,
        article1=article1,
        article2=article2,
        outing1=outing1,
        outing2=outing2,
        outing3=outing3,
        topo_map1=topo_map1,
        topo_map2=topo_map2,
        area1=area1,
        area2=area2,
    )


def test_get_collection(client, session):
    body = scenarios.get_collection(client, session, WAYPOINTS)
    doc = body['documents'][0]
    assert 'waypoint_type' in doc
    assert 'elevation' in doc
    assert 'geometry' in doc
    assert 'routes_quantity' not in doc
    locale = doc['locales'][0]
    assert 'title' in locale
    assert 'summary' in locale
    assert 'description' not in locale
    assert 'areas' in doc


def test_get_collection_lang(client):
    scenarios.get_collection_lang(client, WAYPOINTS)


def test_get_collection_paginated(client, session, docs):
    client.get('/waypoints?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, WAYPOINTS, {'offset': 0, 'limit': 0}),
        [],
        5,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, WAYPOINTS, {'offset': 0, 'limit': 1}),
        [docs.waypoint6.document_id],
        5,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, WAYPOINTS, {'offset': 0, 'limit': 2}),
        [docs.waypoint6.document_id, docs.waypoint4.document_id],
        5,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, WAYPOINTS, {'offset': 1, 'limit': 2}),
        [docs.waypoint4.document_id, docs.waypoint3.document_id],
        5,
    )


def test_get_collection_caching(client, session, docs):
    cache_key_3 = get_cache_key(docs.waypoint3.document_id, None, WAYPOINT_TYPE)
    cache_key_4 = get_cache_key(docs.waypoint4.document_id, None, WAYPOINT_TYPE)
    cache_key_6 = get_cache_key(docs.waypoint6.document_id, None, WAYPOINT_TYPE)

    assert cache_document_listing.get(cache_key_3) == NO_VALUE
    assert cache_document_listing.get(cache_key_4) == NO_VALUE
    assert cache_document_listing.get(cache_key_6) == NO_VALUE

    # check that documents returned in the response are cached
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, WAYPOINTS, {'offset': 0, 'limit': 2}),
        [docs.waypoint6.document_id, docs.waypoint4.document_id],
        5,
    )

    assert cache_document_listing.get(cache_key_4) != NO_VALUE
    assert cache_document_listing.get(cache_key_6) != NO_VALUE

    # check that values are returned from the cache
    fake_cache_value = {'document_id': 'fake_id'}
    cache_document_listing.set(cache_key_3, fake_cache_value)

    body = scenarios.get_collection(
        client, session, WAYPOINTS, {'offset': 1, 'limit': 2}
    )
    scenarios.assert_results_equal(body, [docs.waypoint4.document_id, 'fake_id'], 5)
    assert cache_document_listing.get(cache_key_3) != NO_VALUE


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(
            client, WAYPOINTS, {'wtyp': 'climbing_outdoor,summit'}
        ),
        [
            docs.waypoint4.document_id,
            docs.waypoint3.document_id,
            docs.waypoint2.document_id,
            docs.waypoint.document_id,
        ],
        4,
    )

    body = scenarios.get_collection_search(
        client, WAYPOINTS, {'wtyp': 'climbing_outdoor,summit', 'limit': 2}
    )
    assert body.get('total') == 4
    assert len(body.get('documents')) == 2

    body = scenarios.get_collection_search(
        client, WAYPOINTS, {'a': str(docs.area2.document_id)}
    )
    assert body.get('total') == 1

    body = scenarios.get_collection_search(client, WAYPOINTS, {'walt': '2000'})
    assert body.get('total') == 1


def test_get_collection_search_bbox(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(
            client, WAYPOINTS, {'bbox': '659000,5694000,660000,5695000'}
        ),
        [docs.waypoint4.document_id],
        1,
    )


def test_get_collection_big_offset(client):
    url = f'{WAYPOINTS.prefix}?offset=10000'
    response = client.get(url, status=400)
    assert_errors_contain(response.json, 'Bad Request')

    url = f'{WAYPOINTS.prefix}?offset=9970&limit=30'
    client.get(url, status=200)


def test_get(client, docs):
    body = scenarios.get(client, WAYPOINTS, docs.waypoint, title=docs.locale_en.title)
    _assert_geometry(body)
    assert 'waypoint_type' in body
    assert 'routes_quantity' not in body

    assert 'associations' in body
    associations = body.get('associations')
    assert 'articles' in associations
    assert 'books' in associations
    assert 'images' in associations
    assert 'waypoints' in associations

    linked_articles = associations.get('articles')
    assert len(linked_articles) == 1
    assert docs.article1.document_id == linked_articles[0].get('document_id')

    linked_waypoints = associations.get('waypoint_children')
    assert 1 == len(linked_waypoints)
    assert docs.waypoint4.document_id == linked_waypoints[0].get('document_id')
    assert 'type' in linked_waypoints[0]
    assert 'geometry' in linked_waypoints[0]
    assert 'geom' in linked_waypoints[0].get('geometry')

    all_linked_routes = associations.get('all_routes')
    linked_routes = all_linked_routes['documents']
    assert 2 == len(linked_routes)
    linked_route = linked_routes[1]
    assert 'type' in linked_route
    assert linked_route['document_id'] == docs.route1.document_id
    assert linked_route.get('locales')[0].get('title_prefix') == 'Mont Blanc :'
    assert linked_routes[0]['document_id'] == docs.route3.document_id
    assert 'geometry' in linked_routes[1]
    # TODO not returning `geom_detail` anymore
    assert 'geom' in linked_routes[1].get('geometry')

    assert 'maps' in body
    assert 1 == len(body.get('maps'))
    topo_map = body.get('maps')[0]
    assert 'type' in topo_map
    assert topo_map.get('code') == '3232ET'
    assert topo_map.get('locales')[0].get('title') == 'Belley'

    assert 'areas' in body
    area = body.get('areas')[0]
    assert 'type' in area
    assert area.get('area_type') == 'range'
    assert area.get('locales')[0].get('title') == 'France'

    # TODO `outings` renamed to `documents`
    recent_outings = associations.get('recent_outings')
    assert 2 == recent_outings['total']
    assert 2 == len(recent_outings['documents'])
    assert {docs.outing1.document_id, docs.outing3.document_id} == {
        recent_outings['documents'][0].get('document_id'),
        recent_outings['documents'][1].get('document_id'),
    }
    assert 'type' in recent_outings['documents'][0]

    locale_en = get_locale(body.get('locales'), 'en')
    assert 1 == locale_en.get('topic_id')


def test_get_with_empty_arrays(client, docs):
    """Test-case for https://github.com/c2corg/v6_api/issues/231"""
    assert docs.waypoint2.rock_types == []
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint2.document_id), status=200
    )
    body = response.json
    assert 'rock_types' in body
    assert body['rock_types'] == []


def test_get_edit(client, docs):
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id) + '?e=1', status=200
    )
    body = response.json

    assert 'recent_outings' not in body['associations']
    assert 'maps' in body
    assert 'areas' not in body
    assert 'associations' in body
    associations = body['associations']
    assert 'waypoints' in associations
    assert 'waypoint_children' in associations
    assert 'routes' not in associations
    assert 'images' not in associations


def test_get_version(client, docs):
    scenarios.get_version(client, WAYPOINTS, docs.waypoint, docs.waypoint_version)


def test_get_version_etag(client, docs):
    url = (
        f'{WAYPOINTS.prefix}/{docs.waypoint.document_id!s}/en'
        f'/{docs.waypoint_version.id!s}'
    )
    response = client.get(url, status=200)

    # check that the ETag header is set
    headers = response.headers
    etag = headers.get('ETag')
    assert etag is not None

    # then request the document again with the etag
    headers = {'If-None-Match': etag}
    client.get(url, status=304, headers=headers)


def test_get_version_caching(client, docs):
    url = (
        f'{WAYPOINTS.prefix}/{docs.waypoint.document_id!s}/en'
        f'/{docs.waypoint_version.id!s}'
    )
    cache_key = '{}-{}'.format(
        get_cache_key(docs.waypoint.document_id, 'en', WAYPOINT_TYPE),
        docs.waypoint_version.id,
    )

    cache_value = cache_document_version.get(cache_key)
    assert cache_value == NO_VALUE

    # check that the response is cached
    client.get(url, status=200)

    cache_value = cache_document_version.get(cache_key)
    assert cache_value != NO_VALUE

    # check that values are returned from the cache
    fake_cache_value = {'document': 'fake doc'}
    cache_document_version.set(cache_key, fake_cache_value)

    response = client.get(url, status=200)
    body = response.json
    assert body == fake_cache_value


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, WAYPOINTS, docs.waypoint)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, WAYPOINTS, docs.waypoint)


def test_get_lang(client, docs):
    body = scenarios.get_lang(client, WAYPOINTS, docs.waypoint)

    assert 'Mont Granier' == body.get('locales')[0].get('title')


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, WAYPOINTS, docs.waypoint)


def test_get_404(client):
    scenarios.get_404(client, WAYPOINTS)


def test_get_redirected_wp(client, docs):
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint5.document_id), status=200
    )
    body = response.json

    assert 'redirects_to' in body
    assert body['redirects_to'] == docs.waypoint.document_id
    assert set(body['available_langs']) == set(['en', 'fr'])


def test_get_etag(client, docs):
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id), status=200
    )

    # check that the ETag header is set
    headers = response.headers
    etag = headers.get('ETag')
    assert etag is not None

    # then request the document again with the etag
    headers = {'If-None-Match': etag}
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id),
        status=304,
        headers=headers,
    )


def test_get_caching(client, docs):
    scenarios.get_caching(client, WAYPOINTS, docs.waypoint)


def test_get_cache_down(client, docs):
    """Check that the request does not fail even if Redis errors."""
    detail_cache_mock = patch(
        'c2corg_api.views.document.cache_document_detail.get_or_create',
        side_effect=Exception('Redis down'),
    )
    listings_cache_mock = patch(
        'c2corg_api.views.document_listings.cache_document_listing.get_or_create_multi',
        side_effect=Exception('Redis down'),
    )

    with detail_cache_mock, listings_cache_mock:
        client.get(WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id), status=200)
        assert not caching.cache_status.up


def test_get_cache_down_known(client, docs):
    """Check that no request to the cache is made if a request to the
    cache failed in the last 30 seconds.
    """
    detail_cache_mock = patch(
        'c2corg_api.views.document.cache_document_detail.get_or_create',
        side_effect=Exception('Redis down'),
    )
    listings_cache_mock = patch(
        'c2corg_api.views.document_listings.cache_document_listing.get_or_create_multi',
        side_effect=Exception('Redis down'),
    )

    with detail_cache_mock as fn1, listings_cache_mock as fn2:
        caching.cache_status.request_failure()
        client.get(WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id), status=200)
        assert not fn1.called
        assert not fn2.called


def test_get_info(client, docs):
    body, locale = scenarios.get_info(client, WAYPOINTS, docs.waypoint, 'en')
    assert locale.get('lang') == 'en'


def test_get_info_best_lang(client, docs):
    body, locale = scenarios.get_info(client, WAYPOINTS, docs.waypoint, 'es')
    assert locale.get('lang') == 'fr'


def test_get_info_404(client):
    scenarios.get_info_404(client, WAYPOINTS)


def test_get_info_redirect(client, docs):
    response = client.get(
        WAYPOINTS.prefix + '/' + str(docs.waypoint5.document_id) + '/en/info',
        status=200,
    )
    body = response.json

    assert 'redirects_to' in body
    assert body['redirects_to'] == docs.waypoint.document_id
    assert set(body['available_langs']) == set(['en', 'fr'])


def test_post_error(client):
    body = scenarios.post_error(client, WAYPOINTS, {}, status=422)
    errors = errors_of(body)
    assert len(errors) == 1
    assert_required(errors[0], 'waypoint_type')


def test_post_missing_title(client):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3200,
        'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
        'locales': [{'lang': 'en'}],
    }
    scenarios.post_missing_title(client, WAYPOINTS, body)


def test_post_missing_geometry(client):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3200,
        'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
    }
    scenarios.post_missing_geometry(client, WAYPOINTS, body)


def test_post_missing_geom(client):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3200,
        'geometry': {},
        'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
    }
    scenarios.post_missing_geom(client, WAYPOINTS, body)


def test_post_missing_locales(client):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3200,
        'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
        'locales': [],
    }
    scenarios.post_missing_locales(client, WAYPOINTS, body)


def test_post_same_locale_twice(client):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3200,
        'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
        'locales': [
            {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'},
            {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'},
        ],
    }
    scenarios.post_same_locale_twice(client, WAYPOINTS, body)


def test_post_missing_elevation(client):
    body = {
        'waypoint_type': 'summit',
        'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
        'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
    }
    scenarios.post_missing_field(client, WAYPOINTS, body, 'elevation')


def test_post_non_whitelisted_attribute(client, session):
    body = {
        'waypoint_type': 'summit',
        'elevation': 3779,
        'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
        'protected': True,
        'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
    }
    scenarios.post_non_whitelisted_attribute(client, session, WAYPOINTS, body)


def test_post_missing_content_type(client):
    scenarios.post_missing_content_type(client, WAYPOINTS, {})


def test_post_invalid_waypoint_type(client):
    body_post = {
        'geometry': {
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'swimming-pool',
        'elevation': 3779,
        'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
    }
    body = scenarios.post_error(client, WAYPOINTS, body_post, status=422)
    errors = errors_of(body)
    assert len(errors) == 1
    assert errors[0].get('description').startswith('"swimming-pool" is not one of')
    assert errors[0].get('name') == 'waypoint_type'


def test_post_empty_assoc_in_new_w_document(client, session):
    body = {
        'document_id': 0,
        'version': 2345,
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
            }
        ],
        'associations': {
            'waypoints': [],
            'waypoint_children': [],
            'routes': [],
            'all_routes': {'total': 0, 'documents': []},
            'users': [],
            'recent_outings': {'total': 0, 'documents': []},
            'articles': [],
            'images': [],
            'areas': [],
        },
    }

    body, doc = scenarios.post_success(
        client, session, WAYPOINTS, body, user='moderator'
    )


def test_post_invalid_association_with_personal_article(client, docs):
    body_post = {
        'document_id': 1234,
        'version': 2345,
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
            }
        ],
        'associations': {'articles': [{'document_id': docs.article2.document_id}]},
    }
    body = scenarios.post_error(client, WAYPOINTS, body_post, user='contributor2')
    assert_error(
        body['errors'],
        'Bad Request',
        f'no rights to modify associations with article {docs.article2.document_id}',
    )


def test_post_invalid_association_with_redirected_doc(client, docs):
    body_post = {
        'document_id': 1234,
        'version': 2345,
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
            }
        ],
        'associations': {'waypoints': [{'document_id': docs.waypoint5.document_id}]},
    }
    body = scenarios.post_error(client, WAYPOINTS, body_post, user='contributor2')
    assert_error(
        body['errors'],
        'associations.waypoints',
        f'document "{docs.waypoint5.document_id}" does not exist or is redirected',
    )


def test_post_success(client, session, user_ids, docs):
    body = {
        'document_id': 1234,
        'version': 2345,
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
            }
        ],
        'associations': {
            'waypoint_children': [{'document_id': docs.waypoint2.document_id}]
        },
    }
    waypoint2_cache_key = session.get(CacheVersion, docs.waypoint2.document_id).version

    body, doc = scenarios.post_success(client, session, WAYPOINTS, body)
    _assert_geometry(body, 'geom')

    # test that document_id and version was reset
    assert body.get('document_id') != 1234
    assert body.get('version') == 1
    assert doc.locales[0].id != 3456
    assert body.get('locales')[0].get('version') == 1
    assert doc.geometry.document_id == doc.document_id
    assert doc.geometry.version == 1
    version = doc.versions[0]

    archive_waypoint = version.document_archive
    assert archive_waypoint.waypoint_type == 'summit'
    assert archive_waypoint.elevation == 3779

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == 'Mont Pourri'
    assert archive_locale.access == 'y'

    archive_geometry = version.document_geometry_archive
    assert archive_geometry.version == doc.geometry.version
    assert archive_geometry.document_id == doc.geometry.document_id
    assert archive_geometry.geom is not None
    assert archive_geometry.geom_detail is not None

    # check that a link for intersecting areas is created
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.document_id == doc.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].area_id == docs.area1.document_id

    # check that a link for intersecting maps is created
    links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.document_id == doc.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].topo_map_id == docs.topo_map1.document_id

    # check that a link to the child waypoint is created
    association_wp = session.get(
        Association, (doc.document_id, docs.waypoint2.document_id)
    )
    assert association_wp is not None

    # check that the cache key for wp 2 is incremented, which was included
    # as association
    scenarios.check_cache_version(
        session, docs.waypoint2.document_id, waypoint2_cache_key + 1
    )

    # check that a change is created in the feed
    feed_change = get_feed_change(session, doc.document_id)
    assert feed_change is not None
    assert feed_change.user_ids == [user_ids['contributor']]
    assert feed_change.area_ids == [docs.area1.document_id]


def test_post_wrong_geom_type(client, docs):
    body = {
        'document_id': 1234,
        'version': 2345,
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "LineString", "coordinates": '
            '[[635956, 5723604], [635960, 5723610]]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
            }
        ],
        'associations': {
            'waypoint_children': [{'document_id': docs.waypoint2.document_id}]
        },
    }
    errors = scenarios.post_wrong_geom_type(client, WAYPOINTS, body, status=422)
    assert (
        errors[0]['description']
        == "Invalid geometry type. Expected: ['POINT']. Got: LINESTRING."
    )


def test_put_wrong_document_id(client, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': '...',
                    'access': 'n',
                }
            ],
        }
    }
    scenarios.put_wrong_document_id(client, WAYPOINTS, body)


def test_put_wrong_document_version(client, docs):
    body = {
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': -9999,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': '...',
                    'access': 'n',
                }
            ],
        }
    }
    scenarios.put_wrong_version(client, WAYPOINTS, body, docs.waypoint.document_id)


def test_put_wrong_locale_version(client, docs):
    body = {
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': '...',
                    'access': 'n',
                    'version': -9999,
                }
            ],
        }
    }
    scenarios.put_wrong_version(client, WAYPOINTS, body, docs.waypoint.document_id)


def test_put_wrong_ids(client, docs):
    body = {
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_ids(client, WAYPOINTS, body, docs.waypoint.document_id)


def test_put_no_document(client, docs):
    scenarios.put_no_document(client, WAYPOINTS, docs.waypoint.document_id)


def test_put_missing_elevation(client, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
        },
    }
    scenarios.put_missing_field(client, WAYPOINTS, body, docs.waypoint, 'elevation')


def test_put_success_all(client, session, user_ids, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'orientations': None,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier!',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': {
                'version': docs.waypoint.geometry.version,
                'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
            },
            'associations': {
                'waypoint_children': [{'document_id': docs.waypoint2.document_id}],
                'routes': [{'document_id': docs.route1.document_id}],
                'articles': [{'document_id': docs.article1.document_id}],
            },
        },
    }
    (body, waypoint) = scenarios.put_success_all(
        client,
        session,
        WAYPOINTS,
        body,
        docs.waypoint,
        cache_version=4,
        user='moderator',
        locale_fr=docs.locale_fr,
    )

    assert waypoint.elevation == 1234
    locale_en = waypoint.get_locale('en')
    assert locale_en.description == 'A.'
    assert locale_en.access == 'n'

    # version with lang 'en'
    versions = waypoint.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'Mont Granier!'
    assert archive_locale.access == 'n'

    archive_document_en = version_en.document_archive
    assert archive_document_en.waypoint_type == 'summit'
    assert archive_document_en.elevation == 1234

    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 2

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == 'Mont Granier'
    assert archive_locale.access == 'ouai'

    # check that the title_prefix of an associated route (that the wp
    # it the main wp of) was updated
    route = session.get(Route, docs.route1.document_id)
    route_locale_en = route.get_locale('en')
    assert route_locale_en.title_prefix == 'Mont Granier!'

    # check that the route was updated in the search index
    search_doc = SearchRoute.get(
        id=route.document_id, index=elasticsearch_config['index']
    )
    assert search_doc['title_en'] == 'Mont Granier! : Mont Blanc from the air'

    # check that the links for intersecting areas are updated
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.document_id == docs.waypoint.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].area_id == docs.area1.document_id

    # check that the links for intersecting maps are updated
    links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.document_id == docs.waypoint.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].topo_map_id == docs.topo_map1.document_id

    # check that a link to the child waypoint is created
    association_wp = session.get(
        Association, (waypoint.document_id, docs.waypoint2.document_id)
    )
    assert association_wp is not None

    # check that a link to the child article is created
    association_a = session.get(
        Association, (waypoint.document_id, docs.article1.document_id)
    )
    assert association_a is not None

    # check that the feed change is updated
    feed_change = get_feed_change(session, waypoint.document_id)
    assert feed_change is not None
    assert feed_change.user_ids == [user_ids['contributor']]
    assert feed_change.area_ids == [docs.area1.document_id]


def test_put_success_figures_and_lang_only(client, session, docs):
    body_put = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': None,
        },
    }
    (body, waypoint) = scenarios.put_success_all(
        client,
        session,
        WAYPOINTS,
        body_put,
        docs.waypoint,
        cache_version=3,
        locale_fr=docs.locale_fr,
    )
    document_id = body.get('document_id')
    assert body.get('version') == 2

    session.expire_all()
    # check that a new archive_document was created
    archive_count = (
        session.query(WAYPOINTS.model_archive)
        .filter(WAYPOINTS.model_archive.document_id == document_id)
        .count()
    )
    assert archive_count == 2

    # check that a new archive_document_locale was created
    archive_locale_count = (
        session.query(WAYPOINTS.model_archive_locale)
        .filter(document_id == WAYPOINTS.model_archive_locale.document_id)
        .count()
    )
    assert archive_locale_count == 3

    # check that a new archive_document_geometry was created
    archive_geometry_count = (
        session.query(ArchiveDocumentGeometry)
        .filter(document_id == ArchiveDocumentGeometry.document_id)
        .count()
    )
    assert archive_geometry_count == 1

    assert waypoint.elevation == 1234
    locale_en = waypoint.get_locale('en')
    assert locale_en.description == 'A.'
    assert locale_en.access == 'n'

    # version with lang 'en'
    versions = waypoint.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'Mont Granier'
    assert archive_locale.access == 'n'

    archive_document_en = version_en.document_archive
    assert archive_document_en.waypoint_type == 'summit'
    assert archive_document_en.elevation == 1234

    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 1

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == 'Mont Granier'
    assert archive_locale.access == 'ouai'

    # check that the links to intersecting areas are not updated,
    # because the geometry did not change
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.document_id == docs.waypoint.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].area_id == docs.area2.document_id


def test_put_success_figures_only(client, session, docs):
    """Test updating a document with only changes to the figures."""
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [],
        },
    }
    (body, waypoint) = scenarios.put_success_figures_only(
        client, session, WAYPOINTS, body, docs.waypoint
    )

    assert waypoint.elevation == 1234


def test_put_boolean_default_values(client, session, docs):
    """Test-case for https://github.com/c2corg/v6_api/issues/229"""
    assert docs.waypoint.blanket_unstaffed is None
    assert docs.waypoint.matress_unstaffed is None
    assert docs.waypoint.gas_unstaffed is None
    assert docs.waypoint.heating_unstaffed is None

    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 1234,
            'blanket_unstaffed': True,
            'matress_unstaffed': False,
            'gas_unstaffed': None,
            'locales': [],
        },
    }
    (_, waypoint) = scenarios.put_success_figures_only(
        client, session, WAYPOINTS, body, docs.waypoint
    )

    assert waypoint.blanket_unstaffed is True
    assert waypoint.matress_unstaffed is False
    assert waypoint.gas_unstaffed is None
    assert waypoint.heating_unstaffed is None


def test_put_success_lang_only(client, session, docs):
    """Test updating a document with only changes to a locale."""
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 2203,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': '...',
                    'access': 'no',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, waypoint) = scenarios.put_success_lang_only(
        client, session, WAYPOINTS, body, docs.waypoint
    )

    assert waypoint.get_locale('en').access == 'no'


def test_put_success_new_lang(client, session, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 2203,
            'locales': [
                {
                    'id': 1234,
                    'version': 2345,
                    'lang': 'es',
                    'title': 'Mont Granier',
                    'description': '...',
                    'access': 'si',
                }
            ],
        },
    }
    (body, waypoint) = scenarios.put_success_new_lang(
        client, session, WAYPOINTS, body, docs.waypoint
    )

    assert waypoint.get_locale('es').access == 'si'
    assert waypoint.get_locale('es').version != 2345
    assert waypoint.get_locale('es').id != 1234


def test_put_add_geometry(client, session, user_ids):
    """Tests adding a geometry to a waypoint without geometry."""
    # first create a waypoint with no geometry
    waypoint = Waypoint(waypoint_type='summit', elevation=3779)

    locale_en = WaypointLocale(lang='en', title='Mont Pourri', access='y')
    waypoint.locales.append(locale_en)

    session.add(waypoint)
    session.flush()
    user_id = user_ids['contributor']
    create_new_version(waypoint, user_id)

    # then add a geometry to the waypoint
    body_put = {
        'message': 'Adding geom',
        'document': {
            'document_id': waypoint.document_id,
            'version': waypoint.version,
            'quality': quality_types[1],
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [],
        },
    }
    response = send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(waypoint.document_id),
        body_put,
        status=403,
    )

    headers = auth_headers(username='contributor')
    send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(waypoint.document_id),
        body_put,
        headers=headers,
        status=200,
    )

    response = client.get(
        WAYPOINTS.prefix + '/' + str(waypoint.document_id), status=200
    )
    assert response.content_type == 'application/json'

    body = response.json
    document_id = body.get('document_id')
    assert body.get('version') == body_put.get('document').get('version')

    # check that no new archive_document was created
    session.expire_all()
    document = session.get(WAYPOINTS.model, document_id)

    # check that a new archive_document was created
    archive_count = (
        session.query(WAYPOINTS.model_archive)
        .filter(WAYPOINTS.model_archive.document_id == document_id)
        .count()
    )
    assert archive_count == 1

    # check that no new archive_document_locale was created
    archive_locale_count = (
        session.query(WAYPOINTS.model_archive_locale)
        .filter(document_id == WAYPOINTS.model_archive_locale.document_id)
        .count()
    )
    assert archive_locale_count == 1

    # check that a new archive_document_geometry was created
    archive_locale_count = (
        session.query(ArchiveDocumentGeometry)
        .filter(document_id == ArchiveDocumentGeometry.document_id)
        .count()
    )
    assert archive_locale_count == 1

    # check that new versions were created
    versions = document.versions
    assert len(versions) == 2

    # version with lang 'en'
    version_en = scenarios.get_latest_version('en', versions)

    assert version_en.lang == 'en'

    meta_data_en = version_en.history_metadata
    assert meta_data_en.comment == 'Adding geom'
    assert meta_data_en.written_at is not None


def test_put_merged_wp(client, docs):
    """Tests updating a waypoint with `redirected_to` set."""
    body_put = {
        'message': 'Updating',
        'document': {
            'document_id': docs.waypoint5.document_id,
            'version': docs.waypoint5.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [],
        },
    }

    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(docs.waypoint5.document_id),
        body_put,
        headers=headers,
        status=400,
    )

    errors = response.json.get('errors')
    assert len(errors) == 1
    assert errors[0].get('description') == 'can not update merged document'
    assert errors[0].get('name') == 'Bad Request'


def test_put_protected_no_permission(client, docs):
    """Tests updating a protected waypoint as non-moderator."""
    body_put = {
        'message': 'Updating',
        'document': {
            'document_id': docs.waypoint4.document_id,
            'version': docs.waypoint4.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [],
        },
    }

    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(docs.waypoint4.document_id),
        body_put,
        headers=headers,
        status=403,
    )

    errors = response.json.get('errors')
    assert len(errors) == 1
    assert (
        errors[0].get('description') == 'No permission to change a protected document'
    )
    assert errors[0].get('name') == 'Forbidden'


def test_put_protected_as_moderator(client, docs):
    """Tests updating a protected waypoint as moderator."""
    body_put = {
        'message': 'Updating',
        'document': {
            'document_id': docs.waypoint4.document_id,
            'version': docs.waypoint4.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [],
        },
    }

    headers = auth_headers(username='moderator')
    send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(docs.waypoint4.document_id),
        body_put,
        headers=headers,
        status=200,
    )


def test_put_no_permission_for_association_change(client, docs):
    """Test that non-moderator users can not remove associations."""
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'orientations': None,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier!',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': {
                'version': docs.waypoint.geometry.version,
                'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
            },
            'associations': {
                'waypoint_children': [
                    # association to waypoint 4 is removed
                ],
                'routes': [{'document_id': docs.route1.document_id}],
                'articles': [{'document_id': docs.article1.document_id}],
            },
        },
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id),
        body,
        headers=headers,
        status=400,
    )
    body = response.json

    assert_error(
        body['errors'],
        'Bad Request',
        'no rights to modify associations between document '
        f'w ({docs.waypoint.document_id}) and w ({docs.waypoint4.document_id})',
    )


def test_put_add_new_association(client, session, docs):
    """Test that non-moderator users can add new associations."""
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'waypoint_type': 'summit',
            'elevation': 1234,
            'orientations': None,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier!',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                }
            ],
            'geometry': {
                'version': docs.waypoint.geometry.version,
                'geom': '{"type": "Point", "coordinates": [635957, 5723605]}',
            },
            'associations': {
                'waypoint_children': [
                    {'document_id': docs.waypoint4.document_id},
                    {'document_id': docs.waypoint2.document_id},
                ],
                'routes': [{'document_id': docs.route1.document_id}],
                'articles': [{'document_id': docs.article1.document_id}],
            },
        },
    }
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'put',
        WAYPOINTS.prefix + '/' + str(docs.waypoint.document_id),
        body,
        headers=headers,
        status=200,
    )

    association = session.get(
        Association, (docs.waypoint.document_id, docs.waypoint2.document_id)
    )
    assert association is not None


def _assert_geometry(body, field='geom'):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get(field) is not None

    geom = geometry.get(field)
    point = shape(json.loads(geom))
    assert isinstance(point, Point)
    assert point.x == pytest.approx(635956, abs=5e-8)
    assert point.y == pytest.approx(5723604, abs=5e-8)


def test_history(client, user_ids, docs):
    id = docs.waypoint.document_id
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


def test_history_etag(client, docs):
    id = docs.waypoint.document_id

    response = client.get(f'/document/{id}/history/fr')

    # check that the ETag header is set
    headers = response.headers
    etag = headers.get('ETag')
    assert etag is not None

    # then request the document again with the etag
    headers = {'If-None-Match': etag}
    client.get(f'/document/{id}/history/fr', status=304, headers=headers)


def test_history_caching(client, docs):
    waypoint_id = docs.waypoint.document_id
    cache_key = get_cache_key(waypoint_id, 'fr', DOCUMENT_TYPE)

    cache_value = cache_document_history.get(cache_key)
    assert cache_value == NO_VALUE

    # check that the response is cached
    client.get(f'/document/{waypoint_id}/history/fr', status=200)

    cache_value = cache_document_history.get(cache_key)
    assert cache_value != NO_VALUE

    # check that values are returned from the cache
    fake_cache_value = {'title': 'fake title'}
    cache_document_history.set(cache_key, fake_cache_value)

    response = client.get(f'/document/{waypoint_id}/history/fr', status=200)
    body = response.json
    assert body == fake_cache_value


def test_get_documents_no_version(docs):
    """Test that documents that do not have a version are skipped."""

    def search_documents(_, __):
        documents_ids = [docs.waypoint.document_id, 999, docs.waypoint2.document_id]
        return documents_ids, 3

    body = get_documents(
        waypoint_documents_config,
        meta_params={'lang': None},
        search_documents=search_documents,
    )

    documents = body.get('documents')
    assert len(documents) == 2

    assert documents[0]['document_id'] == docs.waypoint.document_id
    assert documents[1]['document_id'] == docs.waypoint2.document_id


def test_get_documents_redirect(docs):
    """Test that redirected documents are handled correctly."""

    def search_documents(_, __):
        documents_ids = [
            docs.waypoint.document_id,
            docs.waypoint5.document_id,  # with a redirect
            docs.waypoint2.document_id,
        ]
        return documents_ids, 3

    body = get_documents(
        waypoint_documents_config,
        meta_params={'lang': None},
        search_documents=search_documents,
    )

    documents = body.get('documents')
    assert len(documents) == 2

    assert documents[0]['document_id'] == docs.waypoint.document_id
    assert documents[1]['document_id'] == docs.waypoint2.document_id


def test_get_associations_history(client, docs):
    scenarios.get_association_logs(client, docs.waypoint)


def test_get_with_external_resources(client, docs):
    """Test getting a document with locale and external resources."""
    response = scenarios.get(
        client, WAYPOINTS, docs.waypoint4, title=docs.locale_en.title
    )
    locale_en = get_locale(response.get('locales'), 'en')
    assert locale_en.get('external_resources') == 'https://wikipedia.com/en'


def test_put_success_external_resource(client, session, docs):
    """Test updating a document by adding a locale with external resources."""
    external_resources = 'https://wikipedia.com/en'
    body_put = {
        'message': 'Update',
        'document': {
            'document_id': docs.waypoint.document_id,
            'version': docs.waypoint.version,
            'quality': quality_types[1],
            'waypoint_type': 'summit',
            'elevation': 1234,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Granier',
                    'description': 'A.',
                    'access': 'n',
                    'version': docs.locale_en.version,
                    'external_resources': external_resources,
                }
            ],
            'geometry': None,
        },
    }
    (body, waypoint) = scenarios.put_success_all(
        client,
        session,
        WAYPOINTS,
        body_put,
        docs.waypoint,
        cache_version=3,
        locale_fr=docs.locale_fr,
    )
    locale_en = waypoint.get_locale('en')
    assert locale_en.external_resources == external_resources


def test_post_success_external_resource(client, session, docs):
    """Test creating a document with external resources in locale."""
    external_resources = 'https://wikipedia.com/en'
    body = {
        'geometry': {
            'document_id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'waypoint_type': 'summit',
        'elevation': 3779,
        'locales': [
            {
                'id': 3456,
                'version': 4567,
                'lang': 'en',
                'title': 'Mont Pourri',
                'access': 'y',
                'external_resources': external_resources,
            }
        ],
        'associations': {
            'waypoint_children': [{'document_id': docs.waypoint2.document_id}]
        },
    }
    (body, waypoint) = scenarios.post_success(client, session, WAYPOINTS, body)
    locale_en = waypoint.get_locale('en')
    assert locale_en.external_resources == external_resources


def test_update_access_waypoints_pt(client, session, docs):
    """Test updating waypoint public transportation rating"""
    body_put = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.waypoint6.document_id,
            'version': docs.waypoint6.version,
            'waypoint_type': 'access',
            'elevation': docs.waypoint6.elevation,
            'public_transportation_rating': 'good service',
            'geometry': {
                'version': docs.waypoint6.geometry.version,
                'geom': '{"type": "Point", "coordinates": [657403, 5691411]}',
            },
            'associations': {'routes': [{'document_id': docs.route1.document_id}]},
        },
    }
    scenarios.put_success_figures_only(
        client, session, WAYPOINTS, body_put, docs.waypoint6
    )
    session.flush()
    session.refresh(docs.route1)
    session.refresh(docs.waypoint6)
    assert docs.waypoint6.waypoint_type == 'access'
    assert docs.waypoint6.public_transportation_rating == 'good service'
    assert docs.route1.public_transportation_rating == 'good service'
