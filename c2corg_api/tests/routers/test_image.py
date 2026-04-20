"""
Tests for the FastAPI image router (``/v2/images``).

Mirrors ``c2corg_api/tests/views/test_image.py`` — same test
data, same assertions — but exercises the new FastAPI code path
instead of Pyramid/Cornice.
"""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, shape

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestImageFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/images``.

    Mirrors ``TestImageRest`` from ``tests/views/test_image.py``.
    """

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────
    # Test data  (mirrors BaseTestImage._add_test_data)
    # ──────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.image1 = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.locale_en = DocumentLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            document_topic=DocumentTopic(topic_id=1),
        )
        self.locale_fr = DocumentLocale(
            lang='fr', title='Mont Blanc du ciel', description='...'
        )
        self.image1.locales.append(self.locale_en)
        self.image1.locales.append(self.locale_fr)
        self.image1.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.image1)
        self.session.flush()

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article1)
        self.session.flush()
        self.session.add(
            Association.create(
                parent_document=self.article1, child_document=self.image1
            )
        )

        self.book1 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book1)
        self.session.flush()
        self.session.add(
            Association.create(parent_document=self.book1, child_document=self.image1)
        )

        DocumentRest.create_new_version(self.image1, user_id)
        self.image1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.image1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.image2 = Image(
            filename='image2.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image2)

        self.image3 = Image(
            filename='image3.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image3)

        self.image4 = Image(
            filename='image4.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='personal',
        )
        self.image4.locales.append(
            DocumentLocale(
                lang='en', title='Mont Blanc from the air', description='...'
            )
        )
        self.image4.locales.append(
            DocumentLocale(lang='fr', title='Mont Blanc du ciel', description='...')
        )
        self.session.add(self.image4)
        self.session.flush()

        DocumentRest.create_new_version(self.image3, global_userids['contributor2'])
        DocumentRest.create_new_version(self.image4, user_id)

        self.session.add(
            Association.create(parent_document=self.image1, child_document=self.image2)
        )

        self.waypoint = Waypoint(
            waypoint_type='summit',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier (en)', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint)
        self.session.flush()

        self.area = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='France')]
        )
        self.session.add(self.area)
        self.session.flush()
        self.session.add(Association.create(self.area, self.image1))
        self.session.flush()

        self.outing1 = Outing(
            activities=['skitouring'],
            date_start='2016-01-01',
            date_end='2016-01-01',
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing1)
        self.session.flush()
        self.session.add(
            Association.create(parent_document=self.outing1, child_document=self.image1)
        )
        self.session.add(
            Association(
                parent_document_id=global_userids['contributor'],
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing1.document_id,
                child_document_type=OUTING_TYPE,
            )
        )
        self.session.flush()

        # Force SQLAlchemy to reload geometry from DB as WKBElement
        # (raw EWKT strings in the identity map would fail Pydantic
        # validation when model_validate reads from_attributes=True).
        self.session.expire_all()

    # ── Helpers ──────────────────────────────────────────────

    def _post_success_document(self, overrides=None):
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
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        if overrides:
            doc.update(overrides)
        return doc

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body['geometry']
        assert geometry.get('version') is not None
        assert geometry.get('geom') is not None

        geom = geometry['geom']
        point = shape(json.loads(geom))
        assert isinstance(point, Point)
        assert point.x == pytest.approx(635956)
        assert point.y == pytest.approx(5723604)

    # ══════════════════════════════════════════════════════════
    #  GET collection
    # ══════════════════════════════════════════════════════════

    def test_get_collection(self):
        resp = self.client.get('/v2/images')
        assert resp.status_code == 200
        body = resp.json()
        assert 'documents' in body
        assert len(body['documents']) > 0
        doc = body['documents'][0]
        assert 'filename' in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/images?offset=0&limit=0')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body['documents']) == 0

        resp = self.client.get('/v2/images?offset=0&limit=2')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body['documents']) == 2

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/images?pl=en')
        assert resp.status_code == 200

    # ══════════════════════════════════════════════════════════
    #  GET single
    # ══════════════════════════════════════════════════════════

    def test_get(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        self._assert_geometry(body)

        assert 'creator' in body
        creator = body['creator']
        assert global_userids['contributor'] == creator.get('user_id')

        assert 'associations' in body
        associations = body['associations']
        assert 'articles' in associations
        assert 'books' in associations
        assert 'areas' in associations
        assert 'outings' in associations

        linked_articles = associations['articles']
        assert len(linked_articles) == 1
        assert self.article1.document_id == linked_articles[0]['document_id']

        linked_areas = associations['areas']
        assert len(linked_areas) == 1
        assert self.area.document_id == linked_areas[0]['document_id']

        linked_books = associations['books']
        assert len(linked_books) == 1
        assert self.book1.document_id == linked_books[0]['document_id']

        linked_outings = associations['outings']
        assert len(linked_outings) == 1
        assert self.outing1.document_id == linked_outings[0]['document_id']

    def test_get_404(self):
        resp = self.client.get('/v2/images/9999999')
        assert resp.status_code == 404

    def test_get_lang(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales', [])
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        """Request a lang that the document doesn't have → best match."""
        resp = self.client.get(f'/v2/images/{self.image1.document_id}?l=it')
        assert resp.status_code == 200

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body

    # ══════════════════════════════════════════════════════════
    #  GET info
    # ══════════════════════════════════════════════════════════

    def test_get_info(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body.get('locales', [{}])[0]
        assert locale.get('lang') == 'en'

    def test_get_info_404(self):
        resp = self.client.get('/v2/images/9999999/en/info')
        assert resp.status_code == 404

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}/it/info')
        assert resp.status_code == 200

    # ══════════════════════════════════════════════════════════
    #  GET version
    # ══════════════════════════════════════════════════════════

    def test_get_version(self):
        resp = self.client.get(
            f'/v2/images/{self.image1.document_id}/en/{self.image1_version.id}'
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['document']['document_id'] == self.image1.document_id
        assert body['document']['activities'] == ['paragliding']
        assert body['document']['height'] == 1500

    # ══════════════════════════════════════════════════════════
    #  POST
    # ══════════════════════════════════════════════════════════

    def test_post_unauthenticated(self):
        resp = self.client.post('/v2/images', json=self._post_success_document())
        assert resp.status_code == 403

    def test_post_error(self):
        """Empty body fails Pydantic validation (filename required)."""
        resp = self.client.post('/v2/images', json={}, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()

    def test_post_missing_filename(self):
        body = self._post_success_document()
        del body['filename']
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 400

    def test_post_duplicated_filename(self):
        body = self._post_success_document({'filename': 'image.jpg'})
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 400, resp.json()
        errors = resp.json()['errors']
        assert errors[0]['description'] == 'Unique'

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_missing_title(self, post_mock):
        """Images allow missing titles (defaults to '')."""
        body = self._post_success_document()
        del body['locales'][0]['title']
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.json()
        doc_id = resp.json()['document_id']
        doc = self.session.get(Image, doc_id)
        assert doc.locales[0].title == ''

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_non_whitelisted_attribute(self, post_mock):
        body = {
            'filename': 'post_non_whitelisted.jpg',
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'protected': True,
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        }
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.json()
        doc_id = resp.json()['document_id']
        doc = self.session.get(Image, doc_id)
        assert not doc.protected

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=500, reason='test error'),
    )
    def test_post_image_backend_error(self, post_mock):
        resp = self.client.post(
            '/v2/images',
            json=self._post_success_document(),
            headers=self._auth_headers(),
        )
        assert resp.status_code == 500
        errors = resp.json()['errors']
        assert any('test error' in e.get('description', '') for e in errors)

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_success(self, post_mock):
        body = self._post_success_document()
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.json()
        doc_id = resp.json()['document_id']
        doc = self.session.get(Image, doc_id)
        assert doc is not None
        assert doc.filename == 'post_image.jpg'
        assert doc.activities == ['paragliding']
        assert doc.height == 1500

        # Check geometry
        assert doc.geometry is not None
        assert doc.geometry.geom is not None

        # Check locale
        locale_en = doc.get_locale('en')
        assert locale_en is not None
        assert locale_en.title == 'Some nice loop'

        # Check archive
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

        # Check association to waypoint
        association_wp = self.session.get(
            Association, (self.waypoint.document_id, doc.document_id)
        )
        assert association_wp is not None

        # Verify image backend was called
        post_mock.assert_called_once()

    # ══════════════════════════════════════════════════════════
    #  PUT
    # ══════════════════════════════════════════════════════════

    def test_put_unauthenticated(self):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
        )
        assert resp.status_code == 403

    def test_put_wrong_document_id(self):
        resp = self.client.put(
            '/v2/images/9999999',
            json={
                'message': 'Update',
                'document': {
                    'document_id': 9999999,
                    'version': self.image1.version,
                    'filename': 'put_wrong_document_id.jpg',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 404, resp.json()

    def test_put_wrong_document_version(self):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': -9999,
                    'filename': self.image1.filename,
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.json()

    def test_put_wrong_locale_version(self):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
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
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409, resp.json()

    def test_put_wrong_ids(self):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id + 999999,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400, resp.json()

    def test_put_no_document(self):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={},
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_wrong_user(self):
        """Non-moderator, non-creator cannot edit personal images."""
        resp = self.client.put(
            f'/v2/images/{self.image4.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image4.document_id,
                    'version': self.image4.version,
                    'filename': self.image4.filename,
                    'activities': ['skitouring'],
                    'image_type': 'personal',
                    'quality': 'draft',
                    'height': 2000,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': 'A nice picture',
                            'version': self.image4.get_locale('en').version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 403, resp.json()

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_good_user(self, post_mock):
        """Creator of personal image can edit it."""
        resp = self.client.put(
            f'/v2/images/{self.image4.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image4.document_id,
                    'version': self.image4.version,
                    'filename': self.image4.filename,
                    'activities': ['skitouring'],
                    'image_type': 'personal',
                    'quality': 'draft',
                    'height': 2000,
                    'locales': [
                        {
                            'lang': 'en',
                            'description': 'A nice picture',
                            'version': self.image4.get_locale('en').version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.json()

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_success_all(self, post_mock):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 2000,
                    'geometry': {
                        'version': self.image1.geometry.version,
                        'geom': '{"type": "Point", "coordinates": [1, 2]}',
                    },
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': 'New description',
                            'version': self.locale_en.version,
                        }
                    ],
                    'associations': {
                        'waypoints': [{'document_id': self.waypoint.document_id}]
                    },
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()

        self.session.expire_all()
        image = self.session.get(Image, self.image1.document_id)
        assert image.height == 2000
        assert image.geometry is not None

        locale_en = image.get_locale('en')
        assert locale_en.description == 'New description'

        # version with lang 'en'
        versions = image.versions
        version_en = self._get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Blanc from the air'

        archive_document_en = version_en.document_archive
        assert archive_document_en.activities == ['paragliding']
        assert archive_document_en.height == 2000

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = self._get_latest_version('fr', versions)
        archive_locale_fr = version_fr.document_locales_archive
        assert archive_locale_fr.title == 'Mont Blanc du ciel'

        # Check waypoint association
        association_wp = self.session.get(
            Association, (self.waypoint.document_id, image.document_id)
        )
        assert association_wp is not None

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_success_figures_only(self, post_mock):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Changing figures',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 2000,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()
        self.session.expire_all()
        image = self.session.get(Image, self.image1.document_id)
        assert image.height == 2000

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_success_lang_only(self, post_mock):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Changing lang',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': 'New description',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()
        self.session.expire_all()
        image = self.session.get(Image, self.image1.document_id)
        assert image.get_locale('en').description == 'New description'

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_success_new_lang(self, post_mock):
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Adding lang',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
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
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()
        self.session.expire_all()
        image = self.session.get(Image, self.image1.document_id)
        assert image.get_locale('es').description == '...'

    # ══════════════════════════════════════════════════════════
    #  Image-type permission tests
    # ══════════════════════════════════════════════════════════

    def test_change_image_type_collaborative(self):
        """Non-moderator cannot change type of collaborative images."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'personal',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 400, resp.json()

    def test_change_image_type_copyright(self):
        """Non-moderator cannot change type to copyright."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'copyright',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 403, resp.json()

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_change_image_type_copyright_moderator(self, post_mock):
        """Moderator can change type to copyright."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'copyright',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_change_image_type_collaborative_moderator(self, post_mock):
        """Moderator can change type of collaborative images."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'personal',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.json()

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_change_image_type_non_collaborative(self, post_mock):
        """Non-collaborative (personal) images can become collaborative."""
        resp = self.client.put(
            f'/v2/images/{self.image4.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image4.document_id,
                    'version': self.image4.version,
                    'filename': self.image4.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.image4.get_locale('en').version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.json()

    # ── helper ───────────────────────────────────────────────

    @staticmethod
    def _get_latest_version(lang, versions):
        """Return the most recent DocumentVersion for *lang*."""
        return max((v for v in versions if v.lang == lang), key=lambda v: v.id)

    # ══════════════════════════════════════════════════════════
    #  POST missing-title-none
    # ══════════════════════════════════════════════════════════

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_missing_title_none(self, post_mock):
        """title=None is coerced to empty string (same as omitting it)."""
        body = self._post_success_document()
        body['locales'][0]['title'] = None
        resp = self.client.post('/v2/images', json=body, headers=self._auth_headers())
        assert resp.status_code == 200, resp.json()

    # ══════════════════════════════════════════════════════════
    #  GET edit (?e=1)
    # ══════════════════════════════════════════════════════════

    def test_get_edit(self):
        resp = self.client.get(f'/v2/images/{self.image1.document_id}?e=1')
        assert resp.status_code == 200
        body = resp.json()
        assert 'maps' not in body
        assert 'associations' in body
        associations = body['associations']
        assert 'articles' in associations
        assert 'images' in associations

    # ══════════════════════════════════════════════════════════
    #  POST — outing association permission
    # ══════════════════════════════════════════════════════════

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_no_permission_for_outing_association(self, post_mock):
        """contributor2 cannot create an image associated to outing1
        (they are not a participant of that outing)."""
        body = self._post_success_document(
            {'associations': {'outings': [{'document_id': self.outing1.document_id}]}}
        )
        resp = self.client.post(
            '/v2/images', json=body, headers=self._auth_headers('contributor2')
        )
        assert resp.status_code == 400, resp.json()
        errors = resp.json()['errors']
        assert any(
            'no rights to modify associations with outing {}'.format(
                self.outing1.document_id
            )
            in e.get('description', '')
            for e in errors
        )

    # ══════════════════════════════════════════════════════════
    #  PUT — outing-association permission
    # ══════════════════════════════════════════════════════════

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_no_permission_for_outing_association_removal(self, post_mock):
        """contributor2 cannot remove the outing1 association from image1."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Update',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 2000,
                    'associations': {
                        # remove outing association
                        'outings': [],
                        'waypoints': [{'document_id': self.waypoint.document_id}],
                    },
                },
            },
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 400, resp.json()
        errors = resp.json()['errors']
        assert any(
            'no rights to modify associations' in e.get('description', '')
            for e in errors
        )

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_put_success_as_contributor2(self, post_mock):
        """contributor2 can update image fields without touching outing assoc."""
        resp = self.client.put(
            f'/v2/images/{self.image1.document_id}',
            json={
                'message': 'Changing figures',
                'document': {
                    'document_id': self.image1.document_id,
                    'version': self.image1.version,
                    'filename': self.image1.filename,
                    'quality': 'draft',
                    'activities': ['paragliding'],
                    'image_type': 'collaborative',
                    'height': 2000,
                    'locales': [
                        {
                            'lang': 'en',
                            'title': 'Mont Blanc from the air',
                            'description': '...',
                            'version': self.locale_en.version,
                        }
                    ],
                },
            },
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 200, resp.json()
        self.session.expire_all()
        image = self.session.get(Image, self.image1.document_id)
        assert image.height == 2000


# ══════════════════════════════════════════════════════════════
#  Image proxy tests  — /v2/images/proxy/{id}
# ══════════════════════════════════════════════════════════════


class TestImageProxyRouter(BaseTestCase):
    """Mirrors ``TestImageProxyRest`` from ``tests/views/test_image.py``."""

    @classmethod
    def _get_app(cls):
        from c2corg_api.tests.routers import get_real_app

        return get_real_app()

    def setUp(self):
        super().setUp()
        from c2corg_api.security.fastapi_security import configure_security

        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _add_test_data(self):
        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.session.add(self.image)
        self.image_svg = Image(
            filename='image.svg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.session.add(self.image_svg)
        self.session.flush()

    def test_get_not_exists(self):
        resp = self.client.get('/v2/images/proxy/999', follow_redirects=False)
        assert resp.status_code == 404

    def test_bad_size(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}?size=badsize',
            follow_redirects=False,
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert 'invalid size' == errors[0]['description']

    def test_success_without_size(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}', follow_redirects=False
        )
        assert resp.status_code == 302
        assert 'image.jpg' in resp.headers['location']

    def test_success_with_size(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}?size=BI', follow_redirects=False
        )
        assert resp.status_code == 302
        assert 'imageBI.jpg' in resp.headers['location']

    def test_svg_without_size(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image_svg.document_id}', follow_redirects=False
        )
        assert resp.status_code == 302
        assert 'image.svg' in resp.headers['location']

    def test_svg_with_size(self):
        """SVG files are served as JPEG when a size is requested."""
        resp = self.client.get(
            f'/v2/images/proxy/{self.image_svg.document_id}?size=BI',
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert 'imageBI.jpg' in resp.headers['location']

    def test_bad_extension(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}?size=BI&extension=badextension',
            follow_redirects=False,
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert 'invalid extension' == errors[0]['description']

    def test_format_without_size(self):
        """extension without size is invalid."""
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}?extension=webp',
            follow_redirects=False,
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert 'invalid extension' == errors[0]['description']

    def test_format_with_size(self):
        resp = self.client.get(
            f'/v2/images/proxy/{self.image.document_id}?size=BI&extension=avif',
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert 'imageBI.avif' in resp.headers['location']


# ══════════════════════════════════════════════════════════════
#  Image list (bulk) tests  — /v2/images/list
# ══════════════════════════════════════════════════════════════


class TestImageListRouter(BaseTestCase):
    """Mirrors ``TestImageListRest`` from ``tests/views/test_image.py``."""

    @classmethod
    def _get_app(cls):
        from c2corg_api.tests.routers import get_real_app

        return get_real_app()

    def setUp(self):
        super().setUp()
        from c2corg_api.security.fastapi_security import configure_security

        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _add_test_data(self):
        from c2corg_api.models.association import Association
        from c2corg_api.models.document import DocumentGeometry
        from c2corg_api.models.feed import update_feed_document_create
        from c2corg_api.models.outing import Outing, OutingLocale
        from c2corg_api.models.user_profile import USERPROFILE_TYPE
        from c2corg_api.models.waypoint import Waypoint, WaypointLocale

        user_id = global_userids['contributor']

        self.waypoint = Waypoint(
            waypoint_type='summit',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier (en)', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint)
        self.session.flush()
        update_feed_document_create(self.waypoint, user_id)
        self.session.flush()

        self.outing1 = Outing(
            activities=['skitouring'],
            date_start='2016-01-01',
            date_end='2016-01-01',
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing1)
        self.session.flush()
        self.session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing1.document_id,
                child_document_type='o',
            )
        )
        from c2corg_api.models.feed import update_feed_document_create

        update_feed_document_create(self.outing1, user_id)
        self.session.flush()

    def _post_success_document(self, overrides=None):
        doc = {
            'filename': 'post_image.jpg',
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        if overrides:
            doc.update(overrides)
        return doc

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_multiple(self, post_mock):
        """Two images linked to same waypoint → feed updated with both."""
        from c2corg_api.models.feed import DocumentChange

        body = {
            'images': [
                self._post_success_document(
                    {'filename': 'post_image2.jpg', 'locales': [{'lang': 'en'}]}
                ),
                self._post_success_document({'filename': 'post_image1.jpg'}),
            ]
        }
        resp = self.client.post(
            '/v2/images/list', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.json()
        images_out = resp.json()['images']
        assert len(images_out) == 2

        feed_change = (
            self.session.query(DocumentChange)
            .filter(DocumentChange.document_id == self.waypoint.document_id)
            .order_by(DocumentChange.time.desc())
            .first()
        )
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id
        assert feed_change.image3_id is None

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_multiple_for_outing(self, post_mock):
        """Image linked to outing → feed entry for that outing."""
        from c2corg_api.models.feed import DocumentChange

        body = {
            'images': [
                self._post_success_document(
                    {
                        'filename': 'post_image_outing.jpg',
                        'associations': {
                            'outings': [{'document_id': self.outing1.document_id}]
                        },
                    }
                )
            ]
        }
        resp = self.client.post(
            '/v2/images/list', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 200, resp.json()

        feed_change = (
            self.session.query(DocumentChange)
            .filter(DocumentChange.document_id == self.outing1.document_id)
            .order_by(DocumentChange.time.desc())
            .first()
        )
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is None

    @patch(
        'c2corg_api.routers.image.http_requests.post',
        return_value=Mock(status_code=200),
    )
    def test_post_multiple_as_contributor2(self, post_mock):
        """contributor2 uploading images creates an 'added_photos' entry."""
        from c2corg_api.models.feed import DocumentChange

        user_id = global_userids['contributor2']
        body = {
            'images': [
                self._post_success_document({'filename': 'post_image_c2a.jpg'}),
                self._post_success_document({'filename': 'post_image_c2b.jpg'}),
            ]
        }
        resp = self.client.post(
            '/v2/images/list', json=body, headers=self._auth_headers('contributor2')
        )
        assert resp.status_code == 200, resp.json()

        feed_change = (
            self.session.query(DocumentChange)
            .filter(DocumentChange.document_id == self.waypoint.document_id)
            .filter(DocumentChange.change_type == 'added_photos')
            .filter(DocumentChange.user_id == user_id)
            .first()
        )
        assert feed_change is not None
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id

    def test_post_validation_error(self):
        """Null coordinate in geometry → 400."""
        body = {
            'images': [
                self._post_success_document(
                    {
                        'filename': 'post_validation_error.jpg',
                        'geometry': {
                            'geom': '{"coordinates": [1, null], "type": "Point"}'
                        },
                    }
                )
            ]
        }
        resp = self.client.post(
            '/v2/images/list', json=body, headers=self._auth_headers()
        )
        assert resp.status_code == 400, resp.json()
