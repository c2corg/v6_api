import datetime
import json
from dataclasses import dataclass
from unittest.mock import Mock, patch

import pytest
from shapely.geometry import Point, shape

from c2corg_api.models.area import Area
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.book import Book
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import DocumentChange, update_feed_document_create
from c2corg_api.models.image import IMAGE_TYPE, ArchiveImage, Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
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

IMAGES = DocType('/images', IMAGE_TYPE, Image, ArchiveImage, ArchiveDocumentLocale)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    image: Image
    locale_en: DocumentLocale
    locale_fr: DocumentLocale
    article1: Article
    book1: Book
    image_version: object
    image2: Image
    image3: Image
    image4: Image
    waypoint: Waypoint
    area: Area
    outing1: Outing


@pytest.fixture
def docs(session, user_ids) -> Docs:
    user_id = user_ids['contributor']

    image = Image(
        filename='image.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )

    locale_en = DocumentLocale(
        lang='en',
        title='Mont Blanc from the air',
        description='...',
        document_topic=DocumentTopic(topic_id=1),
    )

    locale_fr = DocumentLocale(lang='fr', title='Mont Blanc du ciel', description='...')

    image.locales.append(locale_en)
    image.locales.append(locale_fr)

    image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')

    session.add(image)
    session.flush()

    article1 = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article1)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=article1, child_document=image),
        user_id,
    )

    book1 = Book(activities=['hiking'], book_types=['biography'])
    session.add(book1)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=book1, child_document=image),
        user_id,
    )

    create_new_version(image, user_id)

    image_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == image.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )

    image2 = Image(filename='image2.jpg', activities=['paragliding'], height=1500)
    session.add(image2)
    image3 = Image(filename='image3.jpg', activities=['paragliding'], height=1500)
    session.add(image3)
    image4 = Image(
        filename='image4.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='personal',
    )
    image4.locales.append(
        DocumentLocale(lang='en', title='Mont Blanc from the air', description='...')
    )
    image4.locales.append(
        DocumentLocale(lang='fr', title='Mont Blanc du ciel', description='...')
    )
    session.add(image4)
    session.flush()
    create_new_version(image3, user_ids['contributor2'])
    create_new_version(image4, user_id)

    scenarios.add_association(
        session,
        Association.create(parent_document=image, child_document=image2),
        user_id,
    )

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
    session.add(waypoint)
    session.flush()
    update_feed_document_create(waypoint, user_id)
    session.flush()

    area = Area(area_type='range', locales=[DocumentLocale(lang='fr', title='France')])
    session.add(area)
    session.flush()

    scenarios.add_association(session, Association.create(area, image), user_id)
    session.flush()

    outing1 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )
    session.add(outing1)
    session.flush()
    scenarios.add_association(
        session,
        Association.create(parent_document=outing1, child_document=image),
        user_id,
    )
    scenarios.add_association(
        session,
        Association(
            parent_document_id=user_ids['contributor'],
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing1.document_id,
            child_document_type=OUTING_TYPE,
        ),
        user_id,
    )
    update_feed_document_create(outing1, user_id)
    session.flush()
    return Docs(
        image=image,
        locale_en=locale_en,
        locale_fr=locale_fr,
        article1=article1,
        book1=book1,
        image_version=image_version,
        image2=image2,
        image3=image3,
        image4=image4,
        waypoint=waypoint,
        area=area,
        outing1=outing1,
    )


def _post_success_document(docs, overrides={}):
    doc = {
        'filename': 'post_image.jpg',
        'activities': ['paragliding'],
        'image_type': 'collaborative',
        'height': 1500,
        'geometry': {
            'id': 5678,
            'version': 6789,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        'associations': {'waypoints': [{'document_id': docs.waypoint.document_id}]},
    }
    doc.update(overrides)
    return doc


def _validate_post_success(docs, session, body, doc, check_wp=True):
    _assert_geometry(body)

    version = doc.versions[0]

    archive_image = version.document_archive
    assert archive_image.activities == ['paragliding']
    assert archive_image.height == 1500

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == 'Some nice loop'

    archive_geometry = version.document_geometry_archive
    assert archive_geometry.version == doc.geometry.version
    assert archive_geometry.geom is not None

    if check_wp:
        # check that a link to the linked wp is created
        association_wp = session.get(
            Association, (docs.waypoint.document_id, doc.document_id)
        )
        assert association_wp is not None


def _assert_geometry(body):
    assert body.get('geometry') is not None
    geometry = body.get('geometry')
    assert geometry.get('version') is not None
    assert geometry.get('geom') is not None

    geom = geometry.get('geom')
    point = shape(json.loads(geom))
    assert isinstance(point, Point)
    assert point.x == pytest.approx(635956, abs=5e-8)
    assert point.y == pytest.approx(5723604, abs=5e-8)


@pytest.mark.usefixtures('docs')
class TestImageRest:
    def test_get_collection(self, client, session, docs):
        body = scenarios.get_collection(client, session, IMAGES)
        doc = body['documents'][0]
        assert 'filename' in doc
        assert 'file_size' not in doc

        # the image type is in the listing, to tell the licence
        by_id = {doc['document_id']: doc for doc in body['documents']}
        image = by_id[docs.image.document_id]
        assert image['image_type'] == 'collaborative'
        # the size of the original, for the UI to keep the thumbnail's space
        assert image['height'] == 1500
        assert 'width' in image
        assert image['license']['id'] == 'CC-BY-SA-3.0'
        image4 = by_id[docs.image4.document_id]
        assert image4['image_type'] == 'personal'
        assert image4['license']['id'] == 'CC-BY-NC-ND-3.0'

    def test_get_collection_paginated(self, client, session, docs):
        client.get('/images?offset=invalid', status=422)

        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, IMAGES, {'offset': 0, 'limit': 0}
            ),
            [],
            4,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, IMAGES, {'offset': 0, 'limit': 1}
            ),
            [docs.image4.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, IMAGES, {'offset': 0, 'limit': 2}
            ),
            [docs.image4.document_id, docs.image3.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, IMAGES, {'offset': 1, 'limit': 2}
            ),
            [docs.image3.document_id, docs.image2.document_id],
            4,
        )

    def test_get_collection_lang(self, client):
        scenarios.get_collection_lang(client, IMAGES)

    def test_get_collection_search(self, client, session, docs):
        reset_search_index(session)

        scenarios.assert_results_equal(
            scenarios.get_collection_search(client, IMAGES, {'l': 'en'}),
            [docs.image4.document_id, docs.image.document_id],
            2,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection_search(client, IMAGES, {'act': 'paragliding'}),
            [
                docs.image4.document_id,
                docs.image3.document_id,
                docs.image2.document_id,
                docs.image.document_id,
            ],
            4,
        )

    def test_get(self, client, user_ids, docs):
        body = scenarios.get(client, IMAGES, docs.image, title=docs.locale_en.title)
        _assert_geometry(body)
        assert body['license']['id'] == 'CC-BY-SA-3.0'
        assert body['license']['attribution_url'].startswith(
            f'http://localhost:6553/images/history/{docs.image.document_id}/'
        )
        assert 'maps' not in body
        locale_en = get_locale(body.get('locales'), 'en')
        assert 1 == locale_en.get('topic_id')

        assert 'creator' in body
        creator = body.get('creator')
        assert user_ids['contributor'] == creator.get('user_id')

        assert 'associations' in body
        associations = body['associations']
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'xreports' in associations
        assert 'images' in associations
        assert 'users' in associations
        assert 'articles' in associations
        assert 'books' in associations
        assert 'areas' in associations
        assert 'outings' in associations

        linked_articles = associations.get('articles')
        assert len(linked_articles) == 1
        assert docs.article1.document_id == linked_articles[0].get('document_id')

        linked_areas = associations.get('areas')
        assert len(linked_areas) == 1
        assert docs.area.document_id == linked_areas[0].get('document_id')

        linked_books = associations.get('books')
        assert len(linked_books) == 1
        assert docs.book1.document_id == linked_books[0].get('document_id')

        linked_outings = associations.get('outings')
        assert len(linked_outings) == 1
        assert docs.outing1.document_id == linked_outings[0].get('document_id')

    def test_get_cooked(self, client, docs):
        scenarios.get_cooked(client, IMAGES, docs.image)

    def test_get_cooked_with_defaulting(self, client, docs):
        scenarios.get_cooked_with_defaulting(client, IMAGES, docs.image)

    def test_get_lang(self, client, docs):
        scenarios.get_lang(client, IMAGES, docs.image)

    def test_get_new_lang(self, client, docs):
        scenarios.get_new_lang(client, IMAGES, docs.image)

    def test_get_404(self, client):
        scenarios.get_404(client, IMAGES)

    def test_get_edit(self, client, docs):
        response = client.get(
            IMAGES.prefix + '/' + str(docs.image.document_id) + '?e=1', status=200
        )
        body = response.json

        assert 'maps' not in body
        assert 'areas' not in body
        assert 'associations' in body
        associations = body['associations']
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'images' in associations
        assert 'users' in associations
        assert 'articles' in associations

    def test_post_error(self, client):
        body = scenarios.post_error(client, IMAGES, {}, status=422)
        errors = errors_of(body)
        assert len(errors) == 1
        assert_required(errors[0], 'filename')

    def test_get_caching(self, client, docs):
        scenarios.get_caching(client, IMAGES, docs.image)

    def test_get_info(self, client, docs):
        body, locale = scenarios.get_info(client, IMAGES, docs.image, 'en')
        assert locale.get('lang') == 'en'

    def test_get_version(self, client, docs):
        scenarios.get_version(client, IMAGES, docs.image, docs.image_version)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_missing_title(self, post_mock, client, session, docs):
        request_body = _post_success_document(docs)
        del request_body['locales'][0]['title']

        body, doc = scenarios.post_success(client, session, IMAGES, request_body)
        assert doc.locales[0].title == ''

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_missing_title_none(self, post_mock, client, session, docs):
        request_body = _post_success_document(docs)
        request_body['locales'][0]['title'] = None

        scenarios.post_success(client, session, IMAGES, request_body)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_non_whitelisted_attribute(self, post_mock, client, session):
        body = {
            'filename': 'post_non_whitelisted.jpg',
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'protected': True,
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        }
        scenarios.post_non_whitelisted_attribute(client, session, IMAGES, body)

    def test_post_missing_content_type(self, client):
        scenarios.post_missing_content_type(client, IMAGES, {})

    def test_post_missing_filename(self, client, docs):
        body_post = _post_success_document(docs)
        del body_post['filename']
        body = scenarios.post_error(client, IMAGES, body_post, status=422)
        errors = errors_of(body)
        assert_required(errors[0], 'filename')

    @pytest.mark.parametrize('value', ['NaN', 'inf', float('nan')])
    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_non_finite_exif(self, post_mock, value, client, session, docs):
        body_post = _post_success_document(docs)
        body_post['fnumber'] = value
        body_post['exposure_time'] = value
        body_post['focal_length'] = 26

        body, doc = scenarios.post_success(client, session, IMAGES, body_post)
        assert doc.fnumber is None
        assert doc.exposure_time is None
        assert doc.focal_length == 26

    def test_get_nan_exif(self, client, session, docs):
        docs.image.fnumber = float('nan')
        docs.image.exposure_time = float('inf')
        session.flush()

        response = client.get(
            IMAGES.prefix + '/' + str(docs.image.document_id), status=200
        )
        assert 'NaN' not in response.text
        assert 'Infinity' not in response.text
        body = response.json
        assert body['fnumber'] is None
        assert body['exposure_time'] is None

    def test_post_duplicated_filename(self, client, docs):
        body_post = _post_success_document(docs)
        body_post['filename'] = 'image.jpg'
        body = scenarios.post_error(client, IMAGES, body_post)
        errors = body.get('errors')
        assert errors[0].get('description') == 'Unique'

    @patch(
        'c2corg_api.views.image.requests.post',
        return_value=Mock(status_code=500, reason='test error'),
    )
    def test_post_image_backend_error(self, post_mock, client, docs):
        headers = auth_headers(username='contributor')
        r = send_json(
            client,
            'post',
            IMAGES.prefix,
            _post_success_document(docs),
            headers=headers,
            status=500,
        )
        assert 'test error' in r.text

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_success(self, post_mock, client, session, docs):
        waypoint_cache_key = session.get(
            CacheVersion, docs.waypoint.document_id
        ).version
        body, doc = scenarios.post_success(
            client, session, IMAGES, _post_success_document(docs)
        )
        _validate_post_success(docs, session, body, doc)
        scenarios.check_cache_version(
            session, docs.waypoint.document_id, waypoint_cache_key + 1
        )

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_no_permission_for_outing_association(self, post_mock, client, docs):
        """Try to create an image with an association to an outing as a user
        who has no permission to add associations to that outing.
        """
        body_post = _post_success_document(
            docs,
            {'associations': {'outings': [{'document_id': docs.outing1.document_id}]}},
        )

        headers = auth_headers(username='contributor2')
        response = send_json(
            client,
            'post',
            IMAGES.prefix,
            body_post,
            headers=headers,
            expect_errors=True,
            status=400,
        )

        body = response.json
        assert_error(
            body.get('errors'),
            'Bad Request',
            f'no rights to modify associations with outing {docs.outing1.document_id}',
        )

    def test_put_wrong_document_id(self, client, docs):
        body = {
            'document': {
                'document_id': '9999999',
                'version': docs.image.version,
                'filename': 'put_wrong_document_id.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_document_id(client, IMAGES, body)

    def test_put_wrong_document_version(self, client, docs):
        body = {
            'document': {
                'document_id': docs.image.document_id,
                'version': -9999,
                'filename': 'put_wrong_document_version.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_version(client, IMAGES, body, docs.image.document_id)

    def test_put_wrong_locale_version(self, client, docs):
        body = {
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': -9999,
                    }
                ],
            }
        }
        scenarios.put_wrong_version(client, IMAGES, body, docs.image.document_id)

    def test_put_wrong_ids(self, client, docs):
        body = {
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_ids(
            client, IMAGES, body, docs.image.document_id, user='moderator'
        )

    def test_put_no_document(self, client, docs):
        scenarios.put_no_document(client, IMAGES, docs.image.document_id)

    def test_put_wrong_user(self, client, docs):
        """Test that a non-moderator user who is not the creator of
        a personal image is not allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image4.document_id,
                'version': docs.image4.version,
                'filename': docs.image4.filename,
                'activities': ['skitouring'],
                'image_type': 'personal',
                'quality': quality_types[1],
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'A nice picture',
                        'version': docs.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = auth_headers(username='contributor2')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image4.document_id),
            body,
            headers=headers,
            status=403,
        )

    def test_put_good_user(self, client, docs):
        """Test that a non-moderator user who is the creator of
        a personal image is allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image4.document_id,
                'version': docs.image4.version,
                'filename': docs.image4.filename,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'image_type': 'personal',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'A nice picture',
                        'version': docs.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image4.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_put_success_all(self, client, session, docs):
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'geometry': {
                    'version': docs.image.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [1, 2]}',
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'New description',
                        'version': docs.locale_en.version,
                    }
                ],
                'associations': {
                    # association to outing is removed
                    'outings': [],
                    'waypoints': [{'document_id': docs.waypoint.document_id}],
                },
            },
        }
        (body, image) = scenarios.put_success_all(
            client,
            session,
            IMAGES,
            body,
            docs.image,
            cache_version=3,
            locale_fr=docs.locale_fr,
        )

        assert image.height == 2000
        locale_en = image.get_locale('en')
        assert locale_en.description == 'New description'

        # version with lang 'en'
        versions = image.versions
        version_en = scenarios.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Blanc from the air'

        archive_document_en = version_en.document_archive
        assert archive_document_en.activities == ['paragliding']
        assert archive_document_en.height == 2000

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = scenarios.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        assert archive_locale.title == 'Mont Blanc du ciel'

        # check that a link to the linked wp is created
        association_wp = session.get(
            Association, (docs.waypoint.document_id, image.document_id)
        )
        assert association_wp is not None

    def test_put_no_permission_for_outing_association_removal(self, client, docs):
        """Try to remove an association with an outing that the user has no
        permission to update the associations of.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'associations': {
                    # association to outing is removed
                    'outings': [],
                    'waypoints': [{'document_id': docs.waypoint.document_id}],
                },
            },
        }

        headers = auth_headers(username='contributor2')
        response = send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image.document_id),
            body,
            headers=headers,
            expect_errors=True,
            status=400,
        )

        body = response.json
        assert_error(
            body.get('errors'),
            'Bad Request',
            'no rights to modify associations between '
            f'document o ({docs.outing1.document_id}) and i ({docs.image.document_id})',
        )

    def test_put_success_as_contributor2(self, client, session, docs):
        """Try to update an image with contributor2 who has no permission to
        change the association to the associated outing, but who can update
        the other fields/associations of the image.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        scenarios.put_success_figures_only(
            client, session, IMAGES, body, docs.image, user='contributor2'
        )

    def test_put_success_figures_only(self, client, session, docs):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        (body, image) = scenarios.put_success_figures_only(
            client, session, IMAGES, body, docs.image
        )

        assert image.height == 2000

    def test_put_success_lang_only(self, client, session, docs):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'New description',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        (body, image) = scenarios.put_success_lang_only(
            client, session, IMAGES, body, docs.image
        )

        assert image.get_locale('en').description == 'New description'

    def test_put_success_new_lang(self, client, session, docs):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'es',
                        'title': 'Mont Blanc del cielo',
                        'description': '...',
                    }
                ],
            },
        }
        (body, image) = scenarios.put_success_new_lang(
            client, session, IMAGES, body, docs.image
        )

        assert image.get_locale('es').description == '...'

    def test_change_image_type_collaborative(self, client, docs):
        """Test that a non-moderator user cannot change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image.document_id),
            body,
            headers=headers,
            status=400,
        )

    def test_change_image_type_copyright(self, client, docs):
        """Test that a non-moderator user cannot change the image_type
        to copyright
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'copyright',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image.document_id),
            body,
            headers=headers,
            status=403,
        )

    def test_change_image_type_copyright_moderator(self, client, docs):
        """Test that a moderator user can change the image_type
        to copyright
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'copyright',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        headers = auth_headers(username='moderator')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_change_image_type_collaborative_moderator(self, client, docs):
        """Test that a moderator can change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image.document_id,
                'version': docs.image.version,
                'filename': docs.image.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.locale_en.version,
                    }
                ],
            },
        }
        headers = auth_headers(username='moderator')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_change_image_type_non_collaborative(self, client, docs):
        """Test that non collaborative images can become collaborative"""
        body = {
            'message': 'Update',
            'document': {
                'document_id': docs.image4.document_id,
                'version': docs.image4.version,
                'filename': docs.image4.filename,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': docs.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'put',
            IMAGES.prefix + '/' + str(docs.image4.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_get_associations_history(self, client, docs):
        scenarios.get_association_logs(client, docs.image)


@pytest.mark.usefixtures('docs')
class TestImageListRest:
    def post_list_success(self, client, session, request_body, user='contributor'):
        response = send_json(client, 'post', '/images/list', request_body, status=403)

        headers = auth_headers(username=user)
        response = send_json(
            client, 'post', '/images/list', request_body, headers=headers, status=200
        )

        body = response.json
        images = body.get('images')
        assert len(request_body['images']) == len(images)
        for image in images:
            (body, doc) = scenarios.validate_document(client, session, IMAGES, image)

        return (body, doc)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_success(self, post_mock, client, session, user_ids, docs):
        body = {'images': [_post_success_document(docs)]}
        body, doc = self.post_list_success(client, session, body)
        _validate_post_success(docs, session, body, doc)

        feed_change = get_feed_change(session, docs.waypoint.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [user_ids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple(self, post_mock, client, session, user_ids, docs):
        body = {
            'images': [
                _post_success_document(
                    docs, {'filename': 'post_image2.jpg', 'locales': [{'lang': 'en'}]}
                ),
                _post_success_document(docs, {'filename': 'post_image1.jpg'}),
            ]
        }
        body, doc = self.post_list_success(client, session, body)
        _validate_post_success(docs, session, body, doc)

        feed_change = get_feed_change(session, docs.waypoint.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [user_ids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id
        assert feed_change.image3_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple_for_outing(self, post_mock, client, session, user_ids, docs):
        body = {
            'images': [
                _post_success_document(
                    docs,
                    {
                        'filename': 'post_image1.jpg',
                        'associations': {
                            'outings': [{'document_id': docs.outing1.document_id}]
                        },
                    },
                )
            ]
        }
        body, doc = self.post_list_success(client, session, body)
        _validate_post_success(docs, session, body, doc, check_wp=False)

        # check that a link to the linked image is created
        association_img = session.get(
            Association, (docs.outing1.document_id, doc.document_id)
        )
        assert association_img is not None

        feed_change = get_feed_change(session, docs.outing1.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [user_ids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is None
        assert feed_change.image3_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple_as_contributor2(
        self, post_mock, client, session, user_ids, docs
    ):
        user_id = user_ids['contributor2']
        body_request = {
            'images': [
                _post_success_document(docs, {'filename': 'post_image1.jpg'}),
                _post_success_document(docs, {'filename': 'post_image2.jpg'}),
            ]
        }
        body, doc = self.post_list_success(
            client, session, body_request, user='contributor2'
        )
        _validate_post_success(docs, session, body, doc)

        feed_change = get_feed_change(
            session, docs.waypoint.document_id, change_type='added_photos'
        )
        assert feed_change is not None
        assert feed_change.change_type == 'added_photos'
        assert feed_change.user_ids == [user_id]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id

        q = (
            session.query(DocumentChange)
            .filter(DocumentChange.document_id == docs.waypoint.document_id)
            .filter(DocumentChange.change_type == 'added_photos')
            .filter(DocumentChange.user_id == user_id)
        )

        assert 1 == q.count()

        # again upload images, and check that there is still only one entry
        body_request = {
            'images': [
                _post_success_document(docs, {'filename': 'post_image3.jpg'}),
                _post_success_document(docs, {'filename': 'post_image4.jpg'}),
            ]
        }
        self.post_list_success(client, session, body_request, user='contributor2')
        assert 1 == q.count()

        session.refresh(feed_change)
        assert feed_change.image3_id is not None
        assert feed_change.more_images

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_validation_error(self, post_mock, client, docs):
        request_body = {
            'images': [
                _post_success_document(
                    docs,
                    {
                        'geometry': {
                            'geom': '{"coordinates": [1, null], "type": "Point"}'
                        }
                    },
                )
            ]
        }

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', '/images/list', request_body, headers=headers, status=422
        )

        body = response.json
        assert_errors_contain(body, 'images.0.geometry.geom')


@dataclass
class ProxyDocs:
    """The documents of the tests, built by `proxy_docs`."""

    image: Image
    image2: Image


@pytest.fixture
def proxy_docs(session) -> ProxyDocs:
    image = Image(
        filename='image.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )
    session.add(image)
    image2 = Image(
        filename='image.svg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )
    session.add(image2)
    session.flush()
    return ProxyDocs(image=image, image2=image2)


@pytest.mark.usefixtures('proxy_docs')
def test_get_not_exists(client):
    client.get(f'/images/proxy/{999}', status=404)


def test_bad_size(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?size=badsize', status=400
    )
    errors = resp.json.get('errors')
    assert 'invalid size' == errors[0].get('description')


def test_success_without_size(client, proxy_docs):
    resp = client.get(f'/images/proxy/{proxy_docs.image.document_id}', status=302)
    assert 'image.jpg' in resp.headers['Location']


def test_success_with_size(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?size=BI', status=302
    )
    assert 'imageBI.jpg' in resp.headers['Location']


def test_svg_without_size(client, proxy_docs):
    resp = client.get(f'/images/proxy/{proxy_docs.image2.document_id}', status=302)
    assert 'image.svg' in resp.headers['Location']


def test_svg_with_size(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image2.document_id}?size=BI', status=302
    )
    assert 'imageBI.jpg' in resp.headers['Location']


def test_bad_extension(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?size=BI&extension=badextension',
        status=400,
    )
    errors = resp.json.get('errors')
    assert 'invalid extension' == errors[0].get('description')


def test_format_without_size(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?extension=webp', status=400
    )
    errors = resp.json.get('errors')
    assert 'invalid extension' == errors[0].get('description')


def test_format_with_size(client, proxy_docs):
    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?size=BI&extension=avif',
        status=302,
    )
    assert 'imageBI.avif' in resp.headers['Location']


def test_merged_image(client, session, proxy_docs):
    # the files of a merged image are deleted, redirect to the target
    merged = Image(
        filename='merged.jpg',
        redirects_to=proxy_docs.image.document_id,
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )
    session.add(merged)
    session.flush()

    resp = client.get(f'/images/proxy/{merged.document_id}?size=BI', status=302)
    assert 'imageBI.jpg' in resp.headers['Location']


@pytest.mark.usefixtures('proxy_docs')
def test_not_an_image(client, session):
    article = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article)
    session.flush()

    client.get(f'/images/proxy/{article.document_id}', status=404)


def test_redirect_is_cacheable(client, proxy_docs):
    resp = client.get(f'/images/proxy/{proxy_docs.image.document_id}', status=302)
    assert 'public, max-age=86400' == resp.headers['Cache-Control']

    resp = client.get(
        f'/images/proxy/{proxy_docs.image.document_id}?size=MI', status=302
    )
    assert 'public, max-age=86400' == resp.headers['Cache-Control']


def test_publish_image_in_backend_sets_a_timeout():
    from c2corg_api.views.image import publish_image_in_backend

    request = Mock()
    request.registry.settings = {
        'image_backend.url': 'http://images.example',
        'image_backend.secret_key': 'secret',
        'url.timeout': '10',
    }
    with patch(
        'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
    ) as post:
        publish_image_in_backend(request, 'image.jpg')
    assert post.call_args.kwargs['timeout'] == 10


def test_publish_image_in_backend_ignores_trailing_slash():
    from c2corg_api.views.image import publish_image_in_backend

    request = Mock()
    request.registry.settings = {
        'image_backend.url': 'http://images.example/',
        'image_backend.secret_key': 'secret',
        'url.timeout': '10',
    }
    with patch(
        'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
    ) as post:
        publish_image_in_backend(request, 'image.jpg')
    assert post.call_args.args[0] == 'http://images.example/publish'
