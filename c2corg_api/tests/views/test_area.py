import json
from dataclasses import dataclass

import pytest
from shapely.geometry import Polygon, shape

from c2corg_api.models.area import AREA_TYPE, ArchiveArea, Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests import assert_required, auth_headers, send_json
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

AREAS = DocType('/areas', AREA_TYPE, Area, ArchiveArea, ArchiveDocumentLocale)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    area1: Area
    locale_en: DocumentLocale
    locale_fr: DocumentLocale
    area1_version: object
    area2: Area
    area3: Area
    area4: Area
    waypoint1: Waypoint
    waypoint2: Waypoint
    route: Route
    image: Image


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    area1 = Area(area_type='range')

    locale_en = DocumentLocale(lang='en', title='Chartreuse')
    locale_fr = DocumentLocale(lang='fr', title='Chartreuse')

    area1.locales.append(locale_en)
    area1.locales.append(locale_fr)

    area1.geometry = DocumentGeometry(
        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
    )

    session.add(area1)
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(area1, user_id)

    area1_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == area1.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )

    area2 = Area(area_type='range')
    session.add(area2)
    area3 = Area(area_type='range')
    session.add(area3)
    area4 = Area(area_type='admin_limits')
    area4.locales.append(DocumentLocale(lang='en', title='Isère'))
    area4.locales.append(DocumentLocale(lang='fr', title='Isère'))
    session.add(area4)

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
    session.add(AreaAssociation(document=waypoint2, area=area1))

    image = Image(
        filename='image.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
        locales=[
            DocumentLocale(
                lang='en', title='Mont Blanc from the air', description='...'
            )
        ],
    )

    session.add(image)
    session.flush()

    scenarios.add_association(session, Association.create(area1, image), user_id)
    session.flush()
    return Docs(
        area1=area1,
        locale_en=locale_en,
        locale_fr=locale_fr,
        area1_version=area1_version,
        area2=area2,
        area3=area3,
        area4=area4,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        route=route,
        image=image,
    )


def test_get_collection(client, session):
    body = scenarios.get_collection(client, session, AREAS)
    doc = body['documents'][0]
    assert 'areas' not in doc
    assert 'geometry' not in doc


def test_get_collection_paginated(client, session, docs):
    client.get('/areas?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, AREAS, {'offset': 0, 'limit': 0}),
        [],
        4,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, AREAS, {'offset': 0, 'limit': 1}),
        [docs.area4.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, AREAS, {'offset': 0, 'limit': 2}),
        [docs.area4.document_id, docs.area3.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, AREAS, {'offset': 1, 'limit': 2}),
        [docs.area3.document_id, docs.area2.document_id],
        4,
    )


def test_get_collection_lang(client):
    scenarios.get_collection_lang(client, AREAS)


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, AREAS, {'l': 'en'}),
        [docs.area4.document_id, docs.area1.document_id],
        2,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, AREAS, {'atyp': 'admin_limits'}),
        [docs.area4.document_id],
        1,
    )


def test_get(client, docs):
    body = scenarios.get(client, AREAS, docs.area1, title=docs.locale_en.title)
    _assert_geometry(body)
    assert 'maps' not in body

    assert 'associations' in body
    associations = body.get('associations')
    assert 'images' in associations
    images = associations.get('images')
    assert 1 == len(images)
    assert images[0].get('document_id') == docs.image.document_id


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, AREAS, docs.area1)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, AREAS, docs.area1)


def test_get_lang(client, docs):
    scenarios.get_lang(client, AREAS, docs.area1)


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, AREAS, docs.area1)


def test_get_404(client):
    scenarios.get_404(client, AREAS)


def test_get_caching(client, docs):
    scenarios.get_caching(client, AREAS, docs.area1)


def test_get_info(client, docs):
    body, locale = scenarios.get_info(client, AREAS, docs.area1, 'en')
    assert locale.get('lang') == 'en'


def test_get_version(client, docs):
    scenarios.get_version(client, AREAS, docs.area1, docs.area1_version)


def test_post_error(client):
    body = scenarios.post_error(client, AREAS, {}, user='moderator')
    errors = body.get('errors')
    assert len(errors) == 3
    assert_required(errors[0], 'locales')
    assert_required(errors[1], 'geometry')
    assert_required(errors[2], 'area_type')


def test_post_missing_title(client):
    body_post = {
        'area_type': 'range',
        'geometry': {
            'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
        },
        'locales': [{'lang': 'en'}],
    }
    scenarios.post_missing_title(client, AREAS, body_post, user='moderator')


def test_post_non_whitelisted_attribute(client, session):
    body = {
        'area_type': 'range',
        'protected': True,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
        },
        'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
    }
    scenarios.post_non_whitelisted_attribute(
        client, session, AREAS, body, user='moderator'
    )


def test_post_missing_content_type(client):
    scenarios.post_missing_content_type(client, AREAS, {})


def test_post_success(client, session, docs):
    body = {
        'area_type': 'range',
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}',  # noqa
        },
        'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
        'associations': {'images': [{'document_id': docs.image.document_id}]},
    }
    body, doc = scenarios.post_success(client, session, AREAS, body, user='moderator')
    _assert_geometry(body)

    version = doc.versions[0]

    archive_map = version.document_archive
    assert archive_map.area_type == 'range'

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == 'Chartreuse'

    archive_geometry = version.document_geometry_archive
    assert archive_geometry.version == doc.geometry.version
    assert archive_geometry.geom_detail is not None

    # check that a link for intersecting documents is created
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == doc.document_id)
        .order_by(AreaAssociation.document_id)
        .all()
    )
    assert len(links) == 2
    assert links[0].document_id == docs.waypoint1.document_id
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    assert links[1].document_id == docs.route.document_id
    scenarios.check_cache_version(session, docs.route.document_id, 2)

    # check that a link to the provided image is created
    association_image = session.get(
        Association, (doc.document_id, docs.image.document_id)
    )
    assert association_image is not None


def test_put_wrong_document_id(client, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.area1.version,
            'area_type': 'range',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Chartreuse',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_document_id(client, AREAS, body)


def test_put_wrong_document_version(client, docs):
    body = {
        'document': {
            'document_id': docs.area1.document_id,
            'version': -9999,
            'area_type': 'range',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Chartreuse',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_version(client, AREAS, body, docs.area1.document_id)


def test_put_wrong_locale_version(client, docs):
    body = {
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'range',
            'locales': [{'lang': 'en', 'title': 'Chartreuse', 'version': -9999}],
        }
    }
    scenarios.put_wrong_version(client, AREAS, body, docs.area1.document_id)


def test_put_wrong_ids(client, docs):
    body = {
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'range',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Chartreuse',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_ids(client, AREAS, body, docs.area1.document_id)


def test_put_no_document(client, docs):
    scenarios.put_no_document(client, AREAS, docs.area1.document_id)


def test_put_update_geometry_fail(client, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'admin_limits',
            'geometry': {
                'version': docs.area1.geometry.version,
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
    headers = auth_headers(username='contributor')
    response = send_json(
        client,
        'put',
        AREAS.prefix + '/' + str(docs.area1.document_id),
        body,
        headers=headers,
        status=400,
    )

    body = response.json
    assert body['status'] == 'error'
    assert body['errors'][0]['name'] == 'Bad Request'
    assert body['errors'][0]['description'] == 'No permission to change the geometry'


def test_put_success_all(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'admin_limits',
            'quality': quality_types[1],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, area) = scenarios.put_success_all(
        client,
        session,
        AREAS,
        body,
        docs.area1,
        cache_version=2,
        locale_fr=docs.locale_fr,
    )

    assert area.area_type == 'admin_limits'
    locale_en = area.get_locale('en')
    assert locale_en.title == 'New title'

    # version with lang 'en'
    versions = area.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'New title'

    archive_document_en = version_en.document_archive
    assert archive_document_en.area_type == 'admin_limits'

    # geometry has not changed because changes to the geometry are not
    # allowed for non-moderators
    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 1

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == 'Chartreuse'


def test_put_success_all_as_moderator(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'admin_limits',
            'quality': quality_types[1],
            'geometry': {
                'version': docs.area1.geometry.version,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
            },
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {'images': []},
        },
    }
    (body, area) = scenarios.put_success_all(
        client,
        session,
        AREAS,
        body,
        docs.area1,
        user='moderator',
        cache_version=3,
        locale_fr=docs.locale_fr,
    )

    # version with lang 'en'
    version_en = area.versions[2]

    # geometry has been changed because the user is a moderator
    archive_geometry_en = version_en.document_geometry_archive
    assert archive_geometry_en.version == 2

    # check that the links to intersecting documents are updated
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area1.document_id)
        .order_by(AreaAssociation.document_id)
        .all()
    )
    assert len(links) == 2
    assert links[0].document_id == docs.waypoint1.document_id
    scenarios.check_cache_version(session, docs.waypoint1.document_id, 2)
    assert links[1].document_id == docs.route.document_id
    scenarios.check_cache_version(session, docs.route.document_id, 2)
    # waypoint 2 is no longer associated, the cache key was incremented
    scenarios.check_cache_version(session, docs.waypoint2.document_id, 2)

    # check that existing link to the image is removed
    association_image = session.get(
        Association, (area.document_id, docs.image.document_id)
    )
    assert association_image is None


def test_put_success_figures_only(client, session, docs):
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'admin_limits',
            'quality': quality_types[1],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Chartreuse',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, area) = scenarios.put_success_figures_only(
        client, session, AREAS, body, docs.area1
    )

    assert area.area_type == 'admin_limits'

    # check that the links to intersecting documents are not updated,
    # because the geometry did not change
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area1.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].document_id == docs.waypoint2.document_id


def test_put_success_lang_only(client, session, docs):
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'range',
            'quality': quality_types[1],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, area) = scenarios.put_success_lang_only(
        client, session, AREAS, body, docs.area1
    )

    assert area.get_locale('en').title == 'New title'

    # check that the links to intersecting documents are not updated,
    # because the geometry did not change
    links = (
        session.query(AreaAssociation)
        .filter(AreaAssociation.area_id == docs.area1.document_id)
        .all()
    )
    assert len(links) == 1
    assert links[0].document_id == docs.waypoint2.document_id


def test_put_success_new_lang(client, session, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.area1.document_id,
            'version': docs.area1.version,
            'area_type': 'range',
            'quality': quality_types[1],
            'locales': [{'lang': 'es', 'title': 'Chartreuse'}],
        },
    }
    (body, area) = scenarios.put_success_new_lang(
        client, session, AREAS, body, docs.area1
    )

    assert area.get_locale('es').title == 'Chartreuse'


def test_get_associations_history(client, docs):
    scenarios.get_association_logs(client, docs.area1)


def _assert_geometry(body):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get('geom_detail') is not None

    geom = geometry.get('geom_detail')
    polygon = shape(json.loads(geom))
    assert isinstance(polygon, Polygon)
