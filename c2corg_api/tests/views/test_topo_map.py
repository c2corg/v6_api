import json
from dataclasses import dataclass

import pytest
from shapely.geometry import Polygon, shape

from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.route import Route
from c2corg_api.models.topo_map import MAP_TYPE, ArchiveTopoMap, TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests import assert_required, auth_headers, send_json
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

MAPS = DocType('/maps', MAP_TYPE, TopoMap, ArchiveTopoMap, ArchiveDocumentLocale)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    map1: TopoMap
    locale_en: DocumentLocale
    locale_fr: DocumentLocale
    map2: TopoMap
    map3: TopoMap
    map4: TopoMap
    waypoint1: Waypoint
    waypoint2: Waypoint
    route: Route


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    map1 = TopoMap(editor='IGN', scale='25000', code='3431OT')

    locale_en = DocumentLocale(lang='en', title="Lac d'Annecy")
    locale_fr = DocumentLocale(lang='fr', title="Lac d'Annecy")

    map1.locales.append(locale_en)
    map1.locales.append(locale_fr)

    map1.geometry = DocumentGeometry(
        geom_detail='SRID=3857;POLYGON((611774 5706934,611774 5744215,'
        '642834 5744215,642834 5706934,611774 5706934))'
    )

    session.add(map1)
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(map1, user_id)

    map2 = TopoMap(editor='IGN', scale='25000', code='3432OT')
    session.add(map2)
    map3 = TopoMap(editor='IGN', scale='25000', code='3433OT')
    session.add(map3)
    map4 = TopoMap(editor='IGN', scale='25000', code='3434OT')
    map4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
    map4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
    session.add(map4)
    session.flush()

    waypoint1 = Waypoint(
        waypoint_type='summit',
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
        ),
    )
    waypoint2 = Waypoint(
        waypoint_type='summit',
        geometry=DocumentGeometry(
            geom='SRID=3857;POINT(693666.031687976 5741108.7574713)'
        ),
    )
    route_geom = 'SRID=3857;LINESTRING(668518 5728802, 668528 5728812)'
    route = Route(
        activities=['skitouring'], geometry=DocumentGeometry(geom_detail=route_geom)
    )

    session.add_all([waypoint1, waypoint2, route])
    session.add(TopoMapAssociation(document=waypoint2, topo_map=map1))
    session.flush()
    return Docs(
        map1=map1,
        locale_en=locale_en,
        locale_fr=locale_fr,
        map2=map2,
        map3=map3,
        map4=map4,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        route=route,
    )


def test_get_collection(client, session):
    body = scenarios.get_collection(client, session, MAPS)
    doc = body['documents'][0]
    assert 'geometry' not in doc


def test_get_collection_paginated(client, session, docs):
    client.get('/maps?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 0}),
        [],
        4,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 1}),
        [docs.map4.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 2}),
        [docs.map4.document_id, docs.map3.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, MAPS, {'offset': 1, 'limit': 2}),
        [docs.map3.document_id, docs.map2.document_id],
        4,
    )


def test_get_collection_lang(client):
    scenarios.get_collection_lang(client, MAPS)


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, MAPS, {'l': 'en'}),
        [docs.map4.document_id, docs.map1.document_id],
        2,
    )


def test_get(client, docs):
    body = scenarios.get(client, MAPS, docs.map1, title=docs.locale_en.title)
    _assert_geometry(body)
    assert 'maps' not in body
    # topo maps are not user content
    assert body['license'] is None


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, MAPS, docs.map1)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, MAPS, docs.map1)


def test_get_lang(client, docs):
    scenarios.get_lang(client, MAPS, docs.map1)


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, MAPS, docs.map1)


def test_get_404(client):
    scenarios.get_404(client, MAPS)


def test_get_caching(client, docs):
    scenarios.get_caching(client, MAPS, docs.map1)


def test_get_info(client, docs):
    body, locale = scenarios.get_info(client, MAPS, docs.map1, 'en')
    assert locale.get('lang') == 'en'


def test_post_not_moderator(client):
    headers = auth_headers(username='contributor')
    send_json(
        client,
        'post',
        MAPS.prefix,
        {},
        headers=headers,
        expect_errors=True,
        status=403,
    )


def test_post_error(client):
    body = scenarios.post_error(client, MAPS, {}, user='moderator')
    errors = body.get('errors')
    assert len(errors) == 2
    assert_required(errors[0], 'locales')
    assert_required(errors[1], 'geometry')


def test_post_missing_title(client):
    body_post = {
        'editor': 'IGN',
        'scale': '25000',
        'code': '3432OT',
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
        },
        'locales': [{'lang': 'en'}],
    }
    scenarios.post_missing_title(client, MAPS, body_post, user='moderator')


def test_post_non_whitelisted_attribute(client, session):
    body = {
        'editor': 'IGN',
        'scale': '25000',
        'code': '3432OT',
        'protected': True,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
        },
        'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
    }
    scenarios.post_non_whitelisted_attribute(
        client, session, MAPS, body, user='moderator'
    )


def test_post_missing_content_type(client):
    scenarios.post_missing_content_type(client, MAPS, {})


def test_post_success(client, session, docs):
    body = {
        'editor': 'IGN',
        'scale': '25000',
        'code': '3432OT',
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}',  # noqa
        },
        'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
    }
    body, doc = scenarios.post_success(client, session, MAPS, body, user='moderator')
    assert body['geometry'].get('geom_detail') is not None

    version = doc.versions[0]

    archive_map = version.document_archive
    assert archive_map.editor == 'IGN'
    assert archive_map.scale == '25000'
    assert archive_map.code == '3432OT'

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == "Lac d'Annecy"

    archive_geometry = version.document_geometry_archive
    assert archive_geometry.version == doc.geometry.version
    assert archive_geometry.geom_detail is not None
    assert archive_geometry.geom_detail is not None

    # check that a link for intersecting documents is created
    links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.topo_map_id == doc.document_id)
        .order_by(TopoMapAssociation.document_id)
        .all()
    )
    assert len(links) == 2
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    scenarios.check_cache_version(session, docs.route.document_id, 2)


def test_put_wrong_document_id(client, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.map1.version,
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_document_id(client, MAPS, body, user='moderator')


def test_put_wrong_document_version(client, docs):
    body = {
        'document': {
            'document_id': docs.map1.document_id,
            'version': -9999,
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_version(
        client, MAPS, body, docs.map1.document_id, user='moderator'
    )


def test_put_wrong_locale_version(client, docs):
    body = {
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
        }
    }
    scenarios.put_wrong_version(
        client, MAPS, body, docs.map1.document_id, user='moderator'
    )


def test_put_wrong_ids(client, docs):
    body = {
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_ids(client, MAPS, body, docs.map1.document_id, user='moderator')


def test_put_no_document(client, docs):
    scenarios.put_no_document(client, MAPS, docs.map1.document_id, user='moderator')


def test_put_success_all(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'quality': quality_types[1],
            'editor': 'IGN',
            'scale': '25000',
            'code': '3433OT',
            'geometry': {
                'version': docs.map1.geometry.version,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
            },
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, map1) = scenarios.put_success_all(
        client,
        session,
        MAPS,
        body,
        docs.map1,
        user='moderator',
        locale_fr=docs.locale_fr,
    )

    assert map1.code == '3433OT'
    locale_en = map1.get_locale('en')
    assert locale_en.title == 'New title'

    # version with lang 'en'
    versions = map1.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'New title'

    archive_document_en = version_en.document_archive
    assert archive_document_en.scale == '25000'
    assert archive_document_en.code == '3433OT'

    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 2

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == "Lac d'Annecy"

    # check that the links to intersecting documents are updated
    links = (
        session.query(TopoMapAssociation)
        .filter(TopoMapAssociation.topo_map_id == docs.map1.document_id)
        .all()
    )
    assert len(links) == 2
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    scenarios.check_cache_version(session, docs.route.document_id, 2)
    # waypoint 2 is no longer associated, the cache key was incremented
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 2)


def test_put_success_figures_only(client, session, docs):
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'quality': quality_types[1],
            'editor': 'IGN',
            'scale': '25000',
            'code': '3433OT',
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, map1) = scenarios.put_success_figures_only(
        client, session, MAPS, body, docs.map1, user='moderator'
    )

    assert map1.code == '3433OT'


def test_put_success_lang_only(client, session, docs):
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'quality': quality_types[1],
            'editor': 'IGN',
            'scale': '25000',
            'code': '3431OT',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, map1) = scenarios.put_success_lang_only(
        client, session, MAPS, body, docs.map1, user='moderator'
    )

    assert map1.get_locale('en').title == 'New title'


def test_put_success_new_lang(client, session, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.map1.document_id,
            'version': docs.map1.version,
            'quality': quality_types[1],
            'editor': 'IGN',
            'scale': '25000',
            'code': '3431OT',
            'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
        },
    }
    (body, map1) = scenarios.put_success_new_lang(
        client, session, MAPS, body, docs.map1, user='moderator'
    )

    assert map1.get_locale('es').title == "Lac d'Annecy"


def _assert_geometry(body):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get('geom_detail') is not None

    geom = geometry.get('geom_detail')
    polygon = shape(json.loads(geom))
    assert isinstance(polygon, Polygon)
