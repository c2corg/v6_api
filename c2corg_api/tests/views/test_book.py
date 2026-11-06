from dataclasses import dataclass

import pytest
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_version
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import BOOK_TYPE, ArchiveBook, Book
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import activities, quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import Image
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests import (
    assert_error,
    assert_required,
    auth_headers,
    errors_of,
    send_json,
)
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

BOOKS = DocType('/books', BOOK_TYPE, Book, ArchiveBook, ArchiveDocumentLocale)


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    book1: Book
    locale_en: DocumentLocale
    locale_fr: DocumentLocale
    book1_version: object
    book2: Book
    book3: Book
    book4: Book
    waypoint1: Waypoint
    waypoint2: Waypoint
    article2: Article
    image: Image
    locale_en_img: DocumentLocale
    locale_fr_img: DocumentLocale
    image2: Image
    route2: Route
    route3: Route


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    book1 = Book(activities=['hiking'], book_types=['biography'])
    locale_en = DocumentLocale(lang='en', title='Escalades au Thaurac')
    locale_fr = DocumentLocale(lang='fr', title='Escalades au Thaurac')

    book1.locales.append(locale_en)
    book1.locales.append(locale_fr)

    session.add(book1)
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(book1, user_id)
    book1_version = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == book1.document_id)
        .filter(DocumentVersion.lang == 'en')
        .first()
    )

    book2 = Book(activities=['hiking'], book_types=['biography'])
    session.add(book2)
    book3 = Book(activities=['hiking'], book_types=['biography'])
    session.add(book3)
    book4 = Book(activities=['hiking'], book_types=['biography'])
    book4.locales.append(DocumentLocale(lang='en', title='Escalades au Thaurac'))
    book4.locales.append(DocumentLocale(lang='fr', title='Escalades au Thaurac'))
    session.add(book4)
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

    article2 = Article(
        categories=['site_info'], activities=['hiking'], article_type='collab'
    )
    session.add(article2)
    session.flush()

    image = Image(
        filename='image.jpg',
        activities=['paragliding'],
        height=1500,
        image_type='collaborative',
    )

    locale_en_img = DocumentLocale(
        lang='en',
        title='Mont Blanc from the air',
        description='...',
        document_topic=DocumentTopic(topic_id=1),
    )

    locale_fr_img = DocumentLocale(
        lang='fr', title='Mont Blanc du ciel', description='...'
    )

    image.locales.append(locale_en_img)
    image.locales.append(locale_fr_img)

    image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')

    session.add(image)
    session.flush()

    image2 = Image(filename='image2.jpg', activities=['paragliding'], height=1500)
    session.add(image2)
    session.flush()

    route2 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        locales=[
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                gear='paraglider',
            ),
            RouteLocale(
                lang='fr',
                title='Mont Blanc du ciel',
                description='...',
                gear='paraglider',
            ),
        ],
    )
    session.add(route2)
    session.flush()

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

    # scenarios.add_association(self.session, Association.create(
    #     parent_document=self.book1,
    #     child_document=self.image2), user_id)
    scenarios.add_association(
        session,
        Association.create(parent_document=book1, child_document=route3),
        user_id,
    )
    scenarios.add_association(
        session,
        Association.create(parent_document=book2, child_document=waypoint2),
        user_id,
    )
    session.flush()
    return Docs(
        book1=book1,
        locale_en=locale_en,
        locale_fr=locale_fr,
        book1_version=book1_version,
        book2=book2,
        book3=book3,
        book4=book4,
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        article2=article2,
        image=image,
        locale_en_img=locale_en_img,
        locale_fr_img=locale_fr_img,
        image2=image2,
        route2=route2,
        route3=route3,
    )


def test_get_collection(client, session):
    body = scenarios.get_collection(client, session, BOOKS)
    doc = body['documents'][0]
    assert 'geometry' not in doc


def test_get_collection_paginated(client, session, docs):
    client.get('/books?offset=invalid', status=422)

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, BOOKS, {'offset': 0, 'limit': 0}),
        [],
        4,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, BOOKS, {'offset': 0, 'limit': 1}),
        [docs.book4.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, BOOKS, {'offset': 0, 'limit': 2}),
        [docs.book4.document_id, docs.book3.document_id],
        4,
    )
    scenarios.assert_results_equal(
        scenarios.get_collection(client, session, BOOKS, {'offset': 1, 'limit': 2}),
        [docs.book3.document_id, docs.book2.document_id],
        4,
    )


def test_get_collection_lang(client):
    scenarios.get_collection_lang(client, BOOKS)


def test_get_collection_search(client, session, docs):
    reset_search_index(session)

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, BOOKS, {'l': 'en'}),
        [docs.book4.document_id, docs.book1.document_id],
        2,
    )

    scenarios.assert_results_equal(
        scenarios.get_collection_search(client, BOOKS, {'btyp': ['biography']}),
        [
            docs.book4.document_id,
            docs.book3.document_id,
            docs.book2.document_id,
            docs.book1.document_id,
        ],
        4,
    )


def test_get(client, docs):
    body = scenarios.get(client, BOOKS, docs.book1, title=docs.locale_en.title)
    assert 'book' not in body
    assert 'geometry' not in body
    assert body.get('geometry') is None
    associations = body['associations']

    assert 'articles' in associations
    assert 'images' in associations
    assert 'routes' in associations
    assert 'waypoints' in associations

    linked_routes = associations.get('routes')
    assert len(linked_routes) == 1

    linked_articles = associations.get('articles')
    assert len(linked_articles) == 0

    linked_images = associations.get('images')
    assert len(linked_images) == 0


def test_get_cooked(client, docs):
    scenarios.get_cooked(client, BOOKS, docs.book1)


def test_get_cooked_with_defaulting(client, docs):
    scenarios.get_cooked_with_defaulting(client, BOOKS, docs.book1)


def test_get_lang(client, docs):
    scenarios.get_lang(client, BOOKS, docs.book1)


def test_get_new_lang(client, docs):
    scenarios.get_new_lang(client, BOOKS, docs.book1)


def test_get_404(client):
    scenarios.get_404(client, BOOKS)


def test_get_version(client, docs):
    scenarios.get_version(client, BOOKS, docs.book1, docs.book1_version)


def test_get_version_etag(client, docs):
    url = f'{BOOKS.prefix}/{docs.book1.document_id!s}/en/{docs.book1_version.id!s}'
    response = client.get(url, status=200)

    # check that the ETag header is set
    headers = response.headers
    etag = headers.get('ETag')
    assert etag is not None

    # then request the document again with the etag
    headers = {'If-None-Match': etag}
    client.get(url, status=304, headers=headers)


def test_get_version_caching(client, docs):
    url = f'{BOOKS.prefix}/{docs.book1.document_id!s}/en/{docs.book1_version.id!s}'
    cache_key = '{}-{}'.format(
        get_cache_key(docs.book1.document_id, 'en', BOOK_TYPE),
        docs.book1_version.id,
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


def test_get_caching(client, docs):
    scenarios.get_caching(client, BOOKS, docs.book1)


def test_get_info(client, docs):
    body, locale = scenarios.get_info(client, BOOKS, docs.book1, 'en')
    assert locale.get('lang') == 'en'


def test_get_info_best_lang(client, docs):
    body, locale = scenarios.get_info(client, BOOKS, docs.book1, 'es')
    assert locale.get('lang') == 'fr'


def test_get_info_404(client):
    scenarios.get_info_404(client, BOOKS)


def test_post_error(client):
    body = scenarios.post_error(client, BOOKS, {}, user='moderator')
    errors = body.get('errors')
    assert len(errors) == 2
    assert_required(errors[0], 'locales')


def test_post_invalid_enum_item(client):
    # an unknown activity used to reach the database enum (500)
    body = {
        'activities': ['hiking', 'not-an-activity'],
        'book_types': ['biography'],
        'locales': [{'lang': 'en', 'title': 'Book'}],
    }
    headers = auth_headers(username='contributor')
    response = send_json(
        client, 'post', BOOKS.prefix, body, headers=headers, status=422
    )
    assert_error(
        errors_of(response.json),
        'activities.1',
        f'"not-an-activity" is not one of {", ".join(activities)}',
    )


def test_post_missing_title(client):
    body_post = {
        'activities': ['hiking'],
        'book_types': ['biography'],
        'locales': [{'lang': 'en'}],
    }
    scenarios.post_missing_title(client, BOOKS, body_post, user='moderator')


def test_post_non_whitelisted_attribute(client, session):
    body = {
        'book_types': ['biography'],
        'protected': True,
        'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
    }
    scenarios.post_non_whitelisted_attribute(
        client, session, BOOKS, body, user='moderator'
    )


def test_post_missing_content_type(client):
    scenarios.post_missing_content_type(client, BOOKS, {})


def test_post_success(client, session, docs):
    body = {
        'document_id': 12345678,
        'version': 98765432,
        'activities': ['hiking'],
        'book_types': ['biography'],
        'author': 'NewAuthor',
        'editor': 'NewEditor',
        'isbn': '12345678',
        'nb_pages': 150,
        'publication_date': '1984',
        'url': 'http://www.nowhere.to.find',
        'associations': {
            'waypoints': [{'document_id': docs.waypoint2.document_id}],
            'articles': [{'document_id': docs.article2.document_id}],
        },
        'geometry': {
            'version': 1,
            'document_id': docs.waypoint2.document_id,
            'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
        },
        'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
    }
    body, doc = scenarios.post_success(client, session, BOOKS, body, user='moderator')
    version = doc.versions[0]

    archive_book = version.document_archive
    assert archive_book.activities == ['hiking']
    assert archive_book.book_types == ['biography']

    archive_locale = version.document_locales_archive
    assert archive_locale.lang == 'en'
    assert archive_locale.title == 'Escalades au Thaurac'

    # check if geometry is not stored in database afterwards
    assert doc.geometry is None

    # check that a link to the associated waypoint is created
    association_wp = session.get(
        Association, (doc.document_id, docs.waypoint2.document_id)
    )
    assert association_wp is not None

    association_wp_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == doc.document_id)
        .filter(AssociationLog.child_document_id == docs.waypoint2.document_id)
        .first()
    )
    assert association_wp_log is not None

    # check that a link to the associated article is created
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


def test_put_wrong_document_id(client, docs):
    body = {
        'document': {
            'document_id': '9999999',
            'version': docs.book1.version,
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Escalades au Thaurac',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_document_id(client, BOOKS, body, user='moderator')


def test_put_wrong_document_version(client, docs):
    body = {
        'document': {
            'document_id': docs.book1.document_id,
            'version': -9999,
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Escalades au Thaurac',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_version(
        client, BOOKS, body, docs.book1.document_id, user='moderator'
    )


def test_put_wrong_locale_version(client, docs):
    body = {
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [
                {'lang': 'en', 'title': 'Escalades au Thaurac', 'version': -9999}
            ],
        }
    }
    scenarios.put_wrong_version(
        client, BOOKS, body, docs.book1.document_id, user='moderator'
    )


def test_put_wrong_ids(client, docs):
    body = {
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Escalades au Thaurac',
                    'version': docs.locale_en.version,
                }
            ],
        }
    }
    scenarios.put_wrong_ids(
        client, BOOKS, body, docs.book1.document_id, user='moderator'
    )


def test_put_no_document(client, docs):
    scenarios.put_no_document(client, BOOKS, docs.book1.document_id, user='moderator')


def test_put_success_all(client, session, docs):
    body = {
        'message': 'Update',
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'quality': quality_types[1],
            'activities': ['hiking'],
            'book_types': ['magazine'],
            'associations': {
                'articles': [{'document_id': docs.article2.document_id}],
                'images': [{'document_id': docs.image2.document_id}],
                'routes': [{'document_id': docs.route2.document_id}],
            },
            'geometry': {
                'version': 1,
                'document_id': docs.waypoint2.document_id,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
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

    (body, book1) = scenarios.put_success_all(
        client,
        session,
        BOOKS,
        body,
        docs.book1,
        user='moderator',
        cache_version=3,
        locale_fr=docs.locale_fr,
    )

    assert book1.activities == ['hiking']
    locale_en = book1.get_locale('en')
    assert locale_en.title == 'New title'

    # version with lang 'en'
    versions = book1.versions
    version_en = scenarios.get_latest_version('en', versions)
    archive_locale = version_en.document_locales_archive
    assert archive_locale.title == 'New title'

    archive_document_en = version_en.document_archive
    assert archive_document_en.activities == ['hiking']
    assert archive_document_en.book_types == ['magazine']

    # version with lang 'fr'
    version_fr = scenarios.get_latest_version('fr', versions)
    archive_locale = version_fr.document_locales_archive
    assert archive_locale.title == 'Escalades au Thaurac'

    # check if geometry is not stored in database afterwards
    assert book1.geometry is None

    # check that a link to the associated image is created
    association_img = session.get(
        Association, (book1.document_id, docs.image2.document_id)
    )
    assert association_img is not None

    association_img_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == book1.document_id)
        .filter(AssociationLog.child_document_id == docs.image2.document_id)
        .first()
    )
    assert association_img_log is not None

    # check that a link to the associated route is created
    association_rou = session.get(
        Association, (book1.document_id, docs.route2.document_id)
    )
    assert association_rou is not None

    association_rou_log = (
        session.query(AssociationLog)
        .filter(AssociationLog.parent_document_id == book1.document_id)
        .filter(AssociationLog.child_document_id == docs.route2.document_id)
        .first()
    )
    assert association_rou_log is not None


def test_put_success_figures_only(client, session, docs):
    body = {
        'message': 'Changing figures',
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'quality': quality_types[1],
            'activities': ['hiking'],
            'book_types': ['biography'],
            'author': 'New author',
            'editor': 'New editor',
        },
    }
    (body, book1) = scenarios.put_success_figures_only(
        client, session, BOOKS, body, docs.book1, user='moderator'
    )

    assert book1.activities == ['hiking']
    assert book1.book_types == ['biography']


def test_put_success_lang_only(client, session, docs):
    body = {
        'message': 'Changing lang',
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'quality': quality_types[1],
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [
                {
                    'lang': 'en',
                    'title': 'New title',
                    'version': docs.locale_en.version,
                }
            ],
        },
    }
    (body, book1) = scenarios.put_success_lang_only(
        client, session, BOOKS, body, docs.book1, user='moderator'
    )

    assert book1.get_locale('en').title == 'New title'


def test_put_success_new_lang(client, session, docs):
    """Test updating a document by adding a new locale."""
    body = {
        'message': 'Adding lang',
        'document': {
            'document_id': docs.book1.document_id,
            'version': docs.book1.version,
            'quality': quality_types[1],
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [{'lang': 'es', 'title': 'Escalades au Thaurac'}],
        },
    }
    (body, book1) = scenarios.put_success_new_lang(
        client, session, BOOKS, body, docs.book1, user='moderator'
    )

    assert book1.get_locale('es').title == 'Escalades au Thaurac'


def test_get_associations_history(client, docs):
    scenarios.get_association_logs(client, docs.book1)
