import datetime
from dataclasses import dataclass

import pytest
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_version
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    ArchiveXreport,
    ArchiveXreportLocale,
    Xreport,
    XreportLocale,
)
from c2corg_api.tests import (
    assert_not_in_enum,
    assert_required,
    auth_headers,
    errors_of,
    get_locale,
    send_json,
)
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

XREPORTS = DocType(
    '/xreports', XREPORT_TYPE, Xreport, ArchiveXreport, ArchiveXreportLocale
)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    xreport1: Xreport
    locale_en: XreportLocale
    locale_fr: XreportLocale
    xreport1_version: object
    xreport2: Xreport
    xreport3: Xreport
    xreport4: Xreport
    article2: Article
    image2: Image
    waypoint1: Waypoint
    waypoint2: Waypoint
    outing3: Outing
    route3: Route


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    xreport1 = Xreport(
        event_activity='skitouring',
        event_type='stone_ice_fall',
        date=datetime.date(2020, 1, 1),
    )
    locale_en = XreportLocale(
        lang='en', title="Lac d'Annecy", place='some place descrip. in english'
    )
    locale_fr = XreportLocale(
        lang='fr', title="Lac d'Annecy", place='some place descrip. in french'
    )

    xreport1.locales.append(locale_en)
    xreport1.locales.append(locale_fr)

    session.add(xreport1)
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(xreport1, user_id)
    xreport1_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == xreport1.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )

    user_id3 = user_ids['contributor3']
    scenarios.add_association(
        session,
        Association(
            parent_document_id=user_id3,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=xreport1.document_id,
            child_document_type=XREPORT_TYPE,
        ),
        user_id,
    )

    xreport2 = Xreport(
        event_activity='skitouring',
        event_type='avalanche',
        nb_participants=5,
        date=datetime.date(2021, 1, 1),
    )
    session.add(xreport2)
    xreport3 = Xreport(
        event_activity='skitouring',
        event_type='avalanche',
        nb_participants=5,
        date=datetime.date(2018, 1, 1),
    )
    session.add(xreport3)
    xreport4 = Xreport(
        event_activity='skitouring',
        event_type='avalanche',
        nb_participants=5,
        nb_impacted=5,
        age=50,
    )
    xreport4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
    xreport4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
    session.add(xreport4)

    article2 = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article2)
    session.flush()

    image2 = Image(filename='image2.jpg', activities=['paragliding'], height=1500)
    session.add(image2)
    session.flush()

    waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
    session.add(waypoint1)
    waypoint2 = Waypoint(
        waypoint_type='climbing_outdoor',
        elevation=2,
        rock_types=[],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    session.add(waypoint2)
    session.flush()

    outing3 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 2, 1),
        date_end=datetime.date(2016, 2, 2),
    )
    session.add(outing3)
    route3 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=500,
        height_diff_down=500,
        durations='1',
    )
    session.add(route3)
    session.flush()

    scenarios.add_association(
        session,
        Association.create(parent_document=outing3, child_document=xreport1),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=route3, child_document=xreport1),
        user_id,
    )
    session.flush()
    return Docs(
        xreport1=xreport1,
        locale_en=locale_en,
        locale_fr=locale_fr,
        xreport1_version=xreport1_version,
        xreport2=xreport2,
        xreport3=xreport3,
        xreport4=xreport4,
        article2=article2,
        image2=image2,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        outing3=outing3,
        route3=route3,
    )


def test_get_collection(client, session):
    body = scenarios.get_collection(client, session, XREPORTS)
    doc = body['documents'][0]
    assert 'geometry' in doc


def test_get_collection_paginated(client, session, docs):
    client.get('/xreports?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, XREPORTS, {'offset': 0, 'limit': 0}),
        [],
        4,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, XREPORTS, {'offset': 0, 'limit': 1}),
        [docs.xreport4.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, XREPORTS, {'offset': 0, 'limit': 2}),
        [docs.xreport4.document_id, docs.xreport3.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, XREPORTS, {'offset': 1, 'limit': 2}),
        [docs.xreport3.document_id, docs.xreport2.document_id],
        4,
    )


def test_get_collection_lang(client):
    scenarios.get_collection_lang(client, XREPORTS)


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, XREPORTS, {'l': 'en'}),
        [docs.xreport4.document_id, docs.xreport1.document_id],
        2,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, XREPORTS, {'act': 'skitouring'}),
        [
            docs.xreport4.document_id,
            docs.xreport3.document_id,
            docs.xreport2.document_id,
            docs.xreport1.document_id,
        ],
        4,
    )


def test_get(client, user_ids, docs):
    body = scenarios.get(
        client,
        XREPORTS,
        docs.xreport1,
        user='moderator',
        title=docs.locale_en.title,
    )
    assert 'xreport' not in body
    assert body['license']['id'] == 'CC-BY-NC-ND-3.0'
    assert 'geometry' in body
    assert body.get('geometry') is None

    assert 'author' in body
    author = body.get('author')
    assert user_ids['contributor'] == author.get('user_id')

    associations = body['associations']
    assert 'images' in associations
    assert 'articles' in associations
    assert 'outings' in associations
    assert 'routes' in associations

    linked_images = associations.get('images')
    assert len(linked_images) == 0
    linked_articles = associations.get('articles')
    assert len(linked_articles) == 0
    linked_outings = associations.get('outings')
    assert len(linked_outings) == 1
    linked_routes = associations.get('routes')
    assert len(linked_routes) == 1

    assert body.get('event_activity') == docs.xreport1.event_activity

    assert 'nb_participants' in body
    assert 'nb_impacted' in body
    assert 'event_type' in body
    assert body.get('event_type') == 'stone_ice_fall'
    assert 'date' in body
    assert body.get('date') == '2020-01-01'

    locale_en = get_locale(body.get('locales'), 'en')
    assert locale_en.get('place') == 'some place descrip. in english'
    locale_fr = get_locale(body.get('locales'), 'fr')
    assert locale_fr.get('place') == 'some place descrip. in french'


def test_get_as_guest(client, docs):
    body = scenarios.get(
        client, XREPORTS, docs.xreport1, user=None, title=docs.locale_en.title
    )

    # common user should not see personal data in the xreport
    assert 'author_status' not in body
    assert 'activity_rate' not in body
    assert 'age' not in body
    assert 'gender' not in body
    assert 'previous_injuries' not in body
    assert 'autonomy' not in body


def test_get_as_contributor_not_author(client, docs):
    body = scenarios.get(
        client,
        XREPORTS,
        docs.xreport1,
        user='contributor2',
        title=docs.locale_en.title,
    )

    # common user should not see personal data in the xreport
    assert 'author_status' not in body
    assert 'activity_rate' not in body
    assert 'age' not in body
    assert 'gender' not in body
    assert 'previous_injuries' not in body
    assert 'autonomy' not in body


def test_get_as_moderator(client, docs):
    body = scenarios.get(
        client,
        XREPORTS,
        docs.xreport1,
        user='moderator',
        title=docs.locale_en.title,
    )

    # moderator can see personal data in the xreport
    assert 'author_status' in body
    assert 'activity_rate' in body
    assert 'age' in body
    assert 'gender' in body
    assert 'previous_injuries' in body
    assert 'autonomy' in body


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, XREPORTS, docs.xreport1)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, XREPORTS, docs.xreport1)


def test_get_lang(client, docs):
    scenarios.get_lang(client, XREPORTS, docs.xreport1, user='contributor')


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, XREPORTS, docs.xreport1, user='moderator')


def test_get_404(client):
    scenarios.get_404(client, XREPORTS, user='moderator')


def test_get_cache_headers(client, docs):
    response = client.get(
        XREPORTS.prefix + '/' + str(docs.xreport1.document_id), status=200
    )
    headers = response.headers
    etag = headers.get('ETag')
    assert etag is not None

    assert response.headers.get('Cache-Control') == 'private'


def test_get_version(client, docs):
    scenarios.get_version(
        client, XREPORTS, docs.xreport1, docs.xreport1_version, user='contributor'
    )


def test_get_version_etag(client, docs):
    request_headers = auth_headers(username='contributor')
    url = (
        f'{XREPORTS.prefix}/{docs.xreport1.document_id!s}/en'
        f'/{docs.xreport1_version.id!s}'
    )
    response = client.get(url, headers=request_headers, status=200)

    # check that the ETag header is set
    headers = response.headers

    # TODO check etag as private
    etag = headers.get('ETag')
    assert etag is not None

    assert response.headers.get('Cache-Control') is None

    # then request the document again with the etag
    request_headers['If-None-Match'] = etag
    response = client.get(url, status=304, headers=request_headers)
    assert response.headers.get('Cache-Control') is None


def test_get_version_caching(client, docs):
    headers = auth_headers(username='contributor')
    url = (
        f'{XREPORTS.prefix}/{docs.xreport1.document_id!s}/en'
        f'/{docs.xreport1_version.id!s}'
    )
    cache_key = '{}-{}'.format(
        get_cache_key(docs.xreport1.document_id, 'en', XREPORT_TYPE),
        docs.xreport1_version.id,
    )

    cache_value = cache_document_version.get(cache_key)
    assert cache_value == NO_VALUE

    # check that the response is cached
    client.get(url, headers=headers, status=200)

    cache_value = cache_document_version.get(cache_key)
    assert cache_value != NO_VALUE

    # check that values are returned from the cache
    fake_cache_value = {'document': 'fake doc'}
    cache_document_version.set(cache_key, fake_cache_value)

    response = client.get(url, headers=headers, status=200)
    body = response.json
    assert body == fake_cache_value


def test_get_caching(client, docs):
    scenarios.get_caching(client, XREPORTS, docs.xreport1)


def test_get_info(client, docs):
    _, locale = scenarios.get_info(client, XREPORTS, docs.xreport1, 'en')
    assert locale.get('lang') == 'en'


def test_get_info_best_lang(client, docs):
    _, locale = scenarios.get_info(client, XREPORTS, docs.xreport1, 'es')
    assert locale.get('lang') == 'fr'


def test_get_info_404(client):
    scenarios.get_info_404(client, XREPORTS)


def test_post_error(client):
    body = scenarios.post_error(client, XREPORTS, {}, user='moderator', status=422)
    errors = errors_of(body)
    assert len(errors) == 1
    assert_required(errors[0], 'event_activity')


def test_post_missing_title(client):
    body_post = {
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 5,
        'locales': [{'lang': 'en'}],
    }
    scenarios.post_missing_title(client, XREPORTS, body_post, user='moderator')


def test_post_non_whitelisted_attribute(client, session):
    body = {
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 5,
        'protected': True,
        'locales': [
            {
                'lang': 'en',
                'place': 'some place description',
                'title': "Lac d'Annecy",
            }
        ],
    }
    scenarios.post_non_whitelisted_attribute(
        client, session, XREPORTS, body, user='moderator'
    )


def test_post_missing_content_type(client):
    scenarios.post_missing_content_type(client, XREPORTS, {})


def test_post_wrong_geom_type(client, docs):
    body = {
        'document_id': 123456,
        'version': 567890,
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 5,
        'associations': {
            'images': [{'document_id': docs.image2.document_id}],
            'articles': [{'document_id': docs.article2.document_id}],
        },
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom': '{"type": "LineString", "coordinates": '
            + '[[635956, 5723604], [635966, 5723644]]}',
        },
        'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
    }
    errors = scenarios.post_wrong_geom_type(client, XREPORTS, body, status=422)
    assert (
        errors[0]['description']
        == "Invalid geometry type. Expected: ['POINT']. Got: LINESTRING."
    )


def test_post_outdated_attributes_error(client):
    outdated_attributes = [
        # api not checking additional parameters,
        # nb_outings raises no error
        # ('nb_outings', 'nb_outings_9'),
        ('autonomy', 'initiator'),
        ('activity_rate', 'activity_rate_10'),
        ('event_type', 'roped_fall'),
        ('event_activity', 'hiking'),
    ]
    for key, value in outdated_attributes:
        body = {
            'document_id': 123456,
            'event_activity': 'skitouring',
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        body[key] = value
        body = scenarios.post_error(
            client, XREPORTS, body, user='moderator', status=422
        )
        errors = errors_of(body)
        assert len(errors) == 1
        assert_not_in_enum(errors[0], key)


def test_post_success(client, session, docs):
    body = {
        'document_id': 123456,
        'version': 567890,
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 5,
        'nb_outings': 'nb_outings9',
        'autonomy': 'autonomous',
        'activity_rate': 'activity_rate_m2',
        'supervision': 'professional_supervision',
        'qualification': 'federal_trainer',
        'associations': {
            'images': [{'document_id': docs.image2.document_id}],
            'articles': [{'document_id': docs.article2.document_id}],
        },
        'geometry': {
            'version': 1,
            'document_id': docs.waypoint2.document_id,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
    }
    body, doc = scenarios.post_success(
        client,
        session,
        XREPORTS,
        body,
        user='moderator',
        validate_with_auth=True,
    )
    version = doc.versions[0]

    archive_xreport = version.document_archive
    assert archive_xreport.event_activity == 'skitouring'
    assert archive_xreport.event_type == 'stone_ice_fall'
    assert archive_xreport.nb_participants == 5
    assert not hasattr(archive_xreport, 'nb_outings')
    # self.assertNotIn('nb_outings', archive_xreport)
    assert archive_xreport.autonomy == 'autonomous'
    assert archive_xreport.activity_rate == 'activity_rate_m2'
    assert archive_xreport.supervision == 'professional_supervision'
    assert archive_xreport.qualification == 'federal_trainer'

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == "Lac d'Annecy"

    # check if geometry is stored in database afterwards
    assert doc.geometry is not None

    # check that a link to the associated waypoint is created
    association_img = session.get(
        Association, (doc.document_id, docs.image2.document_id)
    )
    assert association_img is not None

    association_img_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == doc.document_id)
        .filter(AssociationLog.child_document_id == docs.image2.document_id)
        .first()
    )
    assert association_img_log is not None

    # check that a link to the associated xreport is created
    association_art = session.get(
        Association, (doc.document_id, docs.article2.document_id)
    )
    assert association_art is not None

    association_art_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == doc.document_id)
        .filter(AssociationLog.child_document_id == docs.article2.document_id)
        .first()
    )
    assert association_art_log is not None


def test_post_as_contributor_and_get_as_author(client, session, user_ids, docs):
    body_post = {
        'document_id': 111,
        'version': 1,
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 666,
        'nb_impacted': 666,
        'locales': [
            # {'title': 'Lac d\'Annecy', 'lang': 'fr'},
            {'title': "Lac d'Annecy", 'lang': 'en'}
        ],
    }

    # create document (POST uses GET schema inside validation)
    body_post, doc = scenarios.post_success(
        client, session, XREPORTS, body_post, user='contributor'
    )

    # the contributor is successfully set as author in DB
    user_id = user_ids['contributor']
    version = doc.versions[0]
    meta_data = version.history_metadata
    assert meta_data.user_id == user_id

    # authorized contributor can see personal data in the xreport
    body = scenarios.get(
        client,
        XREPORTS,
        doc,
        user='contributor',
        ignore_checks=True,
        title=docs.locale_en.title,
    )
    assert 'xreport' not in body

    assert 'author_status' in body
    assert 'activity_rate' in body
    assert 'age' in body
    assert 'gender' in body
    assert 'previous_injuries' in body
    assert 'autonomy' in body


def test_post_anonymous(client, session, user_ids):
    client.registry.anonymous_user_id = user_ids['moderator']
    body_post = {
        'document_id': 111,
        'version': 1,
        'event_activity': 'skitouring',
        'event_type': 'stone_ice_fall',
        'nb_participants': 666,
        'nb_impacted': 666,
        'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        'anonymous': True,
    }

    body_post, doc = scenarios.post_success(
        client, session, XREPORTS, body_post, user='contributor'
    )

    # Check that the contributor is not set as author
    user_id = user_ids['contributor']
    version = doc.versions[0]
    meta_data = version.history_metadata
    assert meta_data.user_id != user_id
    assert meta_data.user_id == user_ids['moderator']


def test_put_wrong_document_id(client, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.xreport1.version,
            'event_activity': 'skitouring',
            'event_type': 'avalanche',
            'nb_participants': 5,
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_document_id(client, XREPORTS, body, user='moderator')


def test_put_wrong_document_version(client, docs):
    body = {
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': -9999,
            'event_activity': 'skitouring',
            'event_type': 'avalanche',
            'nb_participants': 5,
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
        client, XREPORTS, body, docs.xreport1.document_id, user='moderator'
    )


def test_put_wrong_locale_version(client, docs):
    body = {
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'event_activity': 'skitouring',
            'event_type': 'avalanche',
            'nb_participants': 5,
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
        }
    }
    scenarios.put_wrong_version(
        client, XREPORTS, body, docs.xreport1.document_id, user='moderator'
    )


def test_put_wrong_ids(client, docs):
    body = {
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'event_activity': 'skitouring',
            'event_type': 'avalanche',
            'nb_participants': 5,
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_ids(
        client, XREPORTS, body, docs.xreport1.document_id, user='moderator'
    )


def test_put_no_document(client, docs):
    scenarios.put_no_document(
        client, XREPORTS, docs.xreport1.document_id, user='moderator'
    )


def test_put_success_all(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 333,
            'nb_impacted': 666,
            'age': 50,
            'rescue': False,
            'associations': {
                'images': [{'document_id': docs.image2.document_id}],
                'articles': [{'document_id': docs.article2.document_id}],
            },
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'place': 'some NEW place descrip. in english',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, xreport1) = scenarios.put_success_all(
        client,
        session,
        XREPORTS,
        body,
        docs.xreport1,
        user='moderator',
        cache_version=3,
        locale_fr=docs.locale_fr,
    )

    assert xreport1.event_activity == 'skitouring'
    locale_en = xreport1.get_locale('en')
    assert locale_en.title == 'New title'

    # version with lang 'en'
    versions = xreport1.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'New title'
    assert archive_locale.place == 'some NEW place descrip. in english'

    archive_document_en = version_en.document_archive
    assert archive_document_en.event_activity == 'skitouring'
    assert archive_document_en.event_type == 'stone_ice_fall'
    assert archive_document_en.nb_participants == 333
    assert archive_document_en.nb_impacted == 666

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == "Lac d'Annecy"

    # check if geometry is stored in database afterwards
    assert xreport1.geometry is not None
    # check that a link to the associated image is created
    association_img = session.get(
        Association, (xreport1.document_id, docs.image2.document_id)
    )
    assert association_img is not None

    association_img_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == xreport1.document_id)
        .filter(AssociationLog.child_document_id == docs.image2.document_id)
        .first()
    )
    assert association_img_log is not None

    # check that a link to the associated article is created
    association_main_art = session.get(
        Association, (xreport1.document_id, docs.article2.document_id)
    )
    assert association_main_art is not None

    association_art_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == xreport1.document_id)
        .filter(AssociationLog.child_document_id == docs.article2.document_id)
        .first()
    )
    assert association_art_log is not None


def test_put_success_figures_only(client, session, docs):
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 333,
            'nb_impacted': 666,
            'age': 50,
            'rescue': False,
            'locales': [
                {
                    'lang': 'en',
                    'title': "Lac d'Annecy",
                    'place': 'some place descrip. in english',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, xreport1) = scenarios.put_success_figures_only(
        client, session, XREPORTS, body, docs.xreport1, user='moderator'
    )

    assert xreport1.event_activity == 'skitouring'


def test_put_success_lang_only(client, session, docs):
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'date': '2020-01-01',
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, xreport1) = scenarios.put_success_lang_only(
        client, session, XREPORTS, body, docs.xreport1, user='moderator'
    )

    assert xreport1.get_locale('en').title == 'New title'


def test_put_success_new_lang(client, session, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'date': '2020-01-01',
            'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
        },
    }
    (body, xreport1) = scenarios.put_success_new_lang(
        client, session, XREPORTS, body, docs.xreport1, user='moderator'
    )

    assert xreport1.get_locale('es').title == "Lac d'Annecy"


def test_put_as_author(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'sport_climbing',  # changed
            'event_type': 'person_fall',  # changed
            'age': 90,  # PERSONAL DATA CHANGED
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Another final EN title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }

    (body, xreport1) = scenarios.put_success_all(
        client,
        session,
        XREPORTS,
        body,
        docs.xreport1,
        user='contributor',
        cache_version=2,
        locale_fr=docs.locale_fr,
    )

    # version with lang 'en'
    versions = xreport1.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'Another final EN title'

    archive_document_en = version_en.document_archive
    assert archive_document_en.event_activity == 'sport_climbing'
    assert archive_document_en.event_type == 'person_fall'
    assert archive_document_en.age == 90


def test_put_as_associated_user(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.xreport1.document_id,
            'version': docs.xreport1.version,
            'quality': quality_types[1],
            'event_activity': 'alpine_climbing',  # changed
            'event_type': 'crevasse_fall',  # changed
            'age': 25,  # PERSONAL DATA CHANGED
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Renamed title by assoc. user',
                    'version': docs.locale_en.version,
                }
            ],
            'associations': {  # added associations
                'articles': [{'document_id': docs.article2.document_id}],
                'routes': [{'document_id': docs.route3.document_id}],
            },
        },
    }

    (body, xreport1) = scenarios.put_success_all(
        client,
        session,
        XREPORTS,
        body,
        docs.xreport1,
        user='contributor3',
        cache_version=3,
        locale_fr=docs.locale_fr,
    )

    # version with lang 'en'
    versions = xreport1.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'Renamed title by assoc. user'

    archive_document_en = version_en.document_archive
    assert archive_document_en.event_activity == 'alpine_climbing'
    assert archive_document_en.event_type == 'crevasse_fall'
    assert archive_document_en.age == 25


def test_put_as_non_author(client, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.xreport4.document_id,
            'version': docs.xreport4.version,
            'quality': quality_types[1],
            'event_activity': 'sport_climbing',
            'event_type': 'person_fall',
            'age': 90,
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Another final EN title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }

    headers = auth_headers(username='contributor2')
    response = send_json(
        client,
        'put',
        XREPORTS.prefix + '/' + str(docs.xreport4.document_id),
        body,
        headers=headers,
        status=403,
    )

    body = response.json
    assert body['status'] == 'error'
    assert len(body['errors']) == 1
    assert body['errors'][0]['name'] == 'Forbidden'


def test_get_associations_history(client, docs):
    scenarios.get_association_logs(client, docs.xreport1)
