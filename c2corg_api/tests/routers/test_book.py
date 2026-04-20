"""
Tests for the FastAPI book router (``/v2/books``).

Mirrors ``c2corg_api/tests/views/test_book.py`` — same test data, same
assertions — but exercises the new FastAPI code path instead of
Pyramid/Cornice.

Uses ``fastapi.testclient.TestClient`` against the **real** application
built by ``create_app()`` so that middleware (CORS, auth, …) and the
full dependency chain are exercised — ensuring behavioural parity with
the legacy Pyramid stack during the migration.

Only ``get_db`` is overridden so that tests share the
transaction-scoped session from ``BaseTestCase`` (per-test rollback).
Authentication uses the real JWT tokens created by ``setup_package()``.
"""

from dogpile.cache.api import NO_VALUE
from fastapi.testclient import TestClient

from c2corg_api.caching import cache_document_detail, cache_document_version
from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.book import BOOK_TYPE, Book
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import Image
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestBookFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/books``.

    Mirrors ``TestBookRest`` from ``tests/views/test_book.py``.
    Runs against the **real** ``create_app()`` so that CORS,
    authentication, and the full middleware stack are exercised.
    """

    # Build the real app once for the whole class (cached in
    # ``get_real_app()`` so it's shared across test modules).

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        # Override only get_db so that all requests use the
        # transaction-scoped session from BaseTestCase (rolled
        # back in tearDown).  Everything else — CORS, auth,
        # routing — stays real. TODO:
        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        # Default client is **unauthenticated**
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        # Remove the override so it doesn't leak between test
        # classes sharing the same app singleton.
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='moderator'):
        """Return an ``Authorization`` header dict for *username*.

        Mirrors ``BaseTestRest.add_authorization_header`` from the
        Pyramid test suite.
        """
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────────────
    # Test data setup (mirrors TestBookRest._add_test_data)
    # ──────────────────────────────────────────────────────────────────

    def _add_test_data(self):
        self.book1 = Book(activities=['hiking'], book_types=['biography'])
        self.locale_en = DocumentLocale(lang='en', title='Escalades au Thaurac')
        self.locale_fr = DocumentLocale(lang='fr', title='Escalades au Thaurac')
        self.book1.locales.append(self.locale_en)
        self.book1.locales.append(self.locale_fr)
        self.session.add(self.book1)
        self.session.flush()

        user_id = global_userids['contributor']
        DocumentRest.create_new_version(self.book1, user_id)
        self.book1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.book1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.book2 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book2)
        self.book3 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book3)
        self.book4 = Book(activities=['hiking'], book_types=['biography'])
        self.book4.locales.append(
            DocumentLocale(lang='en', title='Escalades au Thaurac')
        )
        self.book4.locales.append(
            DocumentLocale(lang='fr', title='Escalades au Thaurac')
        )
        self.session.add(self.book4)

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint2)
        self.session.flush()

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article2)
        self.session.flush()

        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.locale_en_img = DocumentLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            document_topic=DocumentTopic(topic_id=1),
        )
        self.locale_fr_img = DocumentLocale(
            lang='fr', title='Mont Blanc du ciel', description='...'
        )
        self.image.locales.append(self.locale_en_img)
        self.image.locales.append(self.locale_fr_img)
        self.image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.image)
        self.session.flush()

        self.image2 = Image(
            filename='image2.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image2)
        self.session.flush()

        self.route2 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
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
        self.session.add(self.route2)
        self.session.flush()

        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=500,
            height_diff_down=500,
            durations=['1'],
        )
        self.session.add(self.route3)
        self.session.flush()

        self._add_association(
            Association.create(parent_document=self.book1, child_document=self.route3),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.book2, child_document=self.waypoint2
            ),
            user_id,
        )
        self.session.flush()

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    # ──────────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/books')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        assert 'geometry' not in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/books?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/books?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.book4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/books?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.book4.document_id, self.book3.document_id]

        resp = self.client.get('/v2/books?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.book3.document_id, self.book2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/books?pl=es')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        locales = doc.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────────────

    def test_get(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert 'book' not in body
        assert 'geometry' not in body

        associations = body['associations']
        assert 'articles' in associations
        assert 'images' in associations
        assert 'routes' in associations
        assert 'waypoints' in associations

        linked_routes = associations.get('routes')
        assert len(linked_routes) == 1

    def test_get_lang(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        """Request a lang that doesn't exist → empty locales list."""
        resp = self.client.get(f'/v2/books/{self.book1.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/books/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────────

    def test_get_version(self):
        assert self.book1_version is not None
        url = '/v2/books/{}/{}/{}'.format(
            self.book1.document_id, 'en', self.book1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.book1.document_id
        assert body['version']['version_id'] == self.book1_version.id

    # ──────────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.book1.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/books/{self.book1.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/books/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/books', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        assert len(errors) >= 1

    def test_post_missing_title(self):
        body_post = {
            'activities': ['hiking'],
            'book_types': ['biography'],
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/books', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_non_whitelisted_attribute(self):
        """``protected`` is silently ignored on create."""
        body = {
            'book_types': ['biography'],
            'protected': True,
            'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
        }
        resp = self.client.post(
            '/v2/books', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200
        doc_id = resp.json()['document_id']
        doc = self.session.get(Book, doc_id)
        assert doc is not None
        assert not doc.protected

    def test_post_unauthenticated(self):
        """POST without auth → 403."""
        resp = self.client.post(
            '/v2/books',
            json={
                'book_types': ['biography'],
                'locales': [{'lang': 'en', 'title': 'Test'}],
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
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
                'waypoints': [{'document_id': self.waypoint2.document_id}],
                'articles': [{'document_id': self.article2.document_id}],
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
        }
        resp = self.client.post(
            '/v2/books', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Book, doc_id)
        assert doc is not None
        assert doc is not None
        assert doc.activities == ['hiking']
        assert doc.book_types == ['biography']
        assert doc.author == 'NewAuthor'

        # Version was created
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]
        archive_book = version.document_archive
        assert archive_book.activities == ['hiking']
        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Escalades au Thaurac'

        # Books have no geometry
        assert doc.geometry is None

        # Association to waypoint created
        assoc_wp = self.session.get(
            Association, (doc.document_id, self.waypoint2.document_id)
        )
        assert assoc_wp is not None

        assoc_wp_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.waypoint2.document_id)
            .first()
        )
        assert assoc_wp_log is not None

        # Association to article created
        assoc_art = self.session.get(
            Association, (doc.document_id, self.article2.document_id)
        )
        assert assoc_art is not None

    # ──────────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.book1.version,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Escalades au Thaurac',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/books/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.book1.document_id,
                'version': -9999,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Escalades au Thaurac',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [
                    {'lang': 'en', 'title': 'Escalades au Thaurac', 'version': -9999}
                ],
            }
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id != body document_id → 400."""
        body = {
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Escalades au Thaurac',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id + 1}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_no_document(self):
        """Body with message but no document → 400."""
        body = {'message': '...'}
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        """PUT without auth → 403."""
        body = {
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'book_types': ['biography'],
                'locales': [
                    {'lang': 'en', 'title': 'New', 'version': self.locale_en.version}
                ],
            }
        }
        resp = self.client.put(f'/v2/books/{self.book1.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'quality': QualityTypes.draft,
                'activities': ['hiking'],
                'book_types': ['magazine'],
                'associations': {
                    'articles': [{'document_id': self.article2.document_id}],
                    'images': [{'document_id': self.image2.document_id}],
                    'routes': [{'document_id': self.route2.document_id}],
                },
                'geometry': {
                    'version': 1,
                    'document_id': self.waypoint2.document_id,
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        book1 = self.session.get(Book, self.book1.document_id)
        assert book1 is not None

        assert book1.activities == ['hiking']
        assert book1.book_types == ['magazine']
        locale_en = book1.get_locale('en')
        assert locale_en is not None
        assert locale_en.title == 'New title'

        # Versions created
        versions = book1.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        assert version_en.document_locales_archive.title == 'New title'
        assert version_en.document_archive.book_types == ['magazine']

        # Books have no geometry
        assert book1.geometry is None

        # Association to image created
        assoc_img = self.session.get(
            Association, (book1.document_id, self.image2.document_id)
        )
        assert assoc_img is not None

        # Association to route created
        assoc_rou = self.session.get(
            Association, (book1.document_id, self.route2.document_id)
        )
        assert assoc_rou is not None

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'quality': QualityTypes.draft,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'author': 'New author',
                'editor': 'New editor',
            },
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        book1 = self.session.get(Book, self.book1.document_id)
        assert book1 is not None
        assert book1.author == 'New author'
        assert book1.editor == 'New editor'

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'quality': QualityTypes.draft,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        book1 = self.session.get(Book, self.book1.document_id)
        assert book1.get_locale('en').title == 'New title'  # type: ignore

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.book1.document_id,
                'version': self.book1.version,
                'quality': QualityTypes.draft,
                'activities': ['hiking'],
                'book_types': ['biography'],
                'locales': [{'lang': 'es', 'title': 'Escalades au Thaurac'}],
            },
        }
        resp = self.client.put(
            f'/v2/books/{self.book1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        book1 = self.session.get(Book, self.book1.document_id)
        assert book1.get_locale('es').title == 'Escalades au Thaurac'  # type: ignore

    # ──────────────────────────────────────────────────────────────────
    # GET associations history
    # ──────────────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        """GET /v2/associations-history?d={id} returns logs."""
        r = self.client.get(f'/v2/associations-history?d={self.book1.document_id}')
        assert r.status_code == 200
        body = r.json()
        assert 'count' in body
        assert 'associations' in body
        assert body['count'] >= 1

        for log in body['associations']:
            assert 'written_at' in log
            assert 'is_creation' in log
            assert 'user' in log
            assert 'child_document' in log
            assert 'parent_document' in log
            child_id = log['child_document']['document_id']
            parent_id = log['parent_document']['document_id']
            assert (
                child_id == self.book1.document_id
                or parent_id == self.book1.document_id
            )

    # ──────────────────────────────────────────────────────────────────
    # GET detail — caching
    # ──────────────────────────────────────────────────────────────────

    def test_get_caching(self):
        """GET /v2/books/{id} populates the dogpile cache."""
        cache_key = get_cache_key(self.book1.document_id, None, document_type=BOOK_TYPE)
        assert cache_document_detail.get(cache_key) == NO_VALUE

        r = self.client.get(f'/v2/books/{self.book1.document_id}')
        assert r.status_code == 200

        assert cache_document_detail.get(cache_key) != NO_VALUE

    # ──────────────────────────────────────────────────────────────────
    # GET version — ETag
    # ──────────────────────────────────────────────────────────────────

    def test_get_version_etag(self):
        """GET version returns ETag; If-None-Match → 304."""
        assert self.book1_version is not None
        url = '/v2/books/{}/{}/{}'.format(
            self.book1.document_id, 'en', self.book1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        etag = resp.headers.get('etag')
        assert etag is not None

        resp2 = self.client.get(url, headers={'If-None-Match': etag})
        assert resp2.status_code == 304

    # ──────────────────────────────────────────────────────────────────
    # GET version — dogpile cache
    # ──────────────────────────────────────────────────────────────────

    def test_get_version_caching(self):
        """GET version populates cache; fake value is served."""
        assert self.book1_version is not None
        url = '/v2/books/{}/{}/{}'.format(
            self.book1.document_id, 'en', self.book1_version.id
        )
        cache_key = '{}-{}'.format(
            get_cache_key(self.book1.document_id, 'en', BOOK_TYPE),
            self.book1_version.id,
        )

        assert cache_document_version.get(cache_key) == NO_VALUE

        resp = self.client.get(url)
        assert resp.status_code == 200

        assert cache_document_version.get(cache_key) != NO_VALUE

        # Inject fake value and verify it is served
        fake = {'document': 'fake doc'}
        cache_document_version.set(cache_key, fake)

        resp2 = self.client.get(url)
        assert resp2.status_code == 200
        assert resp2.json() == fake
