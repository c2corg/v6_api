"""
Tests for the FastAPI article router (``/v2/articles``).

Mirrors ``c2corg_api/tests/views/test_article.py`` — same test data,
same assertions — but exercises the new FastAPI code path instead of
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
from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class TestArticleFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/articles``.

    Mirrors ``TestArticleRest`` from ``tests/views/test_article.py``.
    Runs against the **real** ``create_app()`` so that CORS,
    authentication, and the full middleware stack are exercised.
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

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────────
    # Test data setup (mirrors TestArticleRest._add_test_data)
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.locale_en = DocumentLocale(lang='en', title="Lac d'Annecy")
        self.locale_fr = DocumentLocale(lang='fr', title="Lac d'Annecy")
        self.article1.locales.append(self.locale_en)
        self.article1.locales.append(self.locale_fr)
        self.session.add(self.article1)
        self.session.flush()

        user_id = global_userids['contributor']
        create_new_version(self.article1, user_id, db=self.session)
        self.article1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.article1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article2)
        self.article3 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article3)
        self.article4 = Article(
            categories=['site_info'], activities=['hiking'], article_type='personal'
        )
        self.article4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.article4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        self.session.add(self.article4)
        self.session.flush()

        create_new_version(self.article4, user_id, db=self.session)
        self.article4_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.article4.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

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

        self._add_association(
            Association.create(
                parent_document=self.article1, child_document=self.article4
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.article3, child_document=self.article1
            ),
            user_id,
        )
        self.session.flush()

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    # ──────────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/articles')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        assert 'geometry' not in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/articles?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/articles?offset=0&limit=1')
        assert resp.status_code == 200
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.article4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/articles?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.article4.document_id, self.article3.document_id]

        resp = self.client.get('/v2/articles?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.article3.document_id, self.article2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/articles?pl=es')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        locales = doc.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────────

    def test_get(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert 'article' not in body
        assert 'geometry' not in body

        assert 'author' in body
        author = body.get('author')
        assert global_userids['contributor'] == author.get('user_id')

        associations = body['associations']
        assert 'articles' in associations
        assert 'books' in associations
        assert 'images' in associations
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'xreports' in associations
        assert 'users' in associations

        linked_articles = associations.get('articles')
        assert len(linked_articles) == 2

    def test_get_lang(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}?l=en')
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        """Request a lang that doesn't exist →
        empty locales list."""
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}?l=it')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get('/v2/articles/9999999')
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────────

    def test_get_version(self):
        assert self.article1_version is not None
        url = '/v2/articles/{}/{}/{}'.format(
            self.article1.document_id, 'en', self.article1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.article1.document_id
        assert body['version']['version_id'] == self.article1_version.id

    # ──────────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.article1.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/articles/{self.article1.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/articles/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation errors for required fields."""
        resp = self.client.post(
            '/v2/articles', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        body = resp.json()
        errors = body['errors']
        assert len(errors) >= 1

    def test_post_missing_title(self):
        body_post = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/articles', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_non_whitelisted_attribute(self):
        """``protected`` is silently ignored on create."""
        body = {
            'article_type': 'collab',
            'protected': True,
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        resp = self.client.post(
            '/v2/articles', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200
        doc_id = resp.json()['document_id']
        doc = self.session.get(Article, doc_id)
        assert doc is not None
        assert not doc.protected

    def test_post_unauthenticated(self):
        """POST without auth → 403."""
        resp = self.client.post(
            '/v2/articles',
            json={
                'article_type': 'collab',
                'locales': [{'lang': 'en', 'title': 'Test'}],
            },
        )
        assert resp.status_code == 403

    def test_post_empty_assoc_in_new_c_document(self):
        body = {
            'document_id': 0,
            'type': '',
            'quality': 'great',
            'activities': ['hiking', 'skitouring'],
            'categories': ['mountain_environment'],
            'article_type': 'collab',
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
            'locales': [
                {
                    'lang': 'en',
                    'title': 'new testing article',
                    'description': 'some description',
                    'summary': 'some summary',
                }
            ],
        }
        resp = self.client.post(
            '/v2/articles', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200
        doc_id = resp.json()['document_id']
        assert doc_id is not None

    def test_post_success(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'associations': {
                'waypoints': [{'document_id': self.waypoint2.document_id}],
                'articles': [{'document_id': self.article2.document_id}],
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        resp = self.client.post(
            '/v2/articles', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Article, doc_id)
        assert doc is not None
        assert doc.categories == ['site_info']
        assert doc.activities == ['hiking']
        assert doc.article_type == 'collab'

        # Version was created
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]
        archive_article = version.document_archive
        assert archive_article.categories == ['site_info']
        assert archive_article.activities == ['hiking']
        assert archive_article.article_type == 'collab'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        # Articles have no geometry
        assert doc.geometry is None

        # Association to waypoint created
        assoc_wp = self.session.get(
            Association, (self.waypoint2.document_id, doc.document_id)
        )
        assert assoc_wp is not None

        assoc_wp_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint2.document_id)
            .filter(AssociationLog.child_document_id == doc.document_id)
            .first()
        )
        assert assoc_wp_log is not None

        # Association to article created
        assoc_art = self.session.get(
            Association, (doc.document_id, self.article2.document_id)
        )
        assert assoc_art is not None

        assoc_art_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert assoc_art_log is not None

    # ──────────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/articles/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': -9999,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
            }
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        """URL id != body document_id → 400."""
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id + 1}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_no_document(self):
        """Body with message but no document → 422."""
        body = {'message': '...'}
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        """PUT without auth → 403."""
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'article_type': 'collab',
                'locales': [
                    {'lang': 'en', 'title': 'New', 'version': self.locale_en.version}
                ],
            }
        }
        resp = self.client.put(f'/v2/articles/{self.article1.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': QualityTypes.draft,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'personal',
                'associations': {
                    'waypoints': [{'document_id': self.waypoint2.document_id}],
                    'articles': [{'document_id': self.article2.document_id}],
                    'images': [],
                },
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
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
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        article1 = self.session.get(Article, self.article1.document_id)

        assert article1.activities == ['hiking']
        locale_en = article1.get_locale('en')
        assert locale_en.title == 'New title'

        # version with lang 'en'
        versions = article1.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        assert version_en.document_locales_archive.title == 'New title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.categories == ['site_info']
        assert archive_document_en.activities == ['hiking']
        assert archive_document_en.article_type == 'personal'

        # Articles have no geometry
        assert article1.geometry is None

        # Association to waypoint created
        assoc_wp = self.session.get(
            Association, (self.waypoint2.document_id, article1.document_id)
        )
        assert assoc_wp is not None

        assoc_wp_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint2.document_id)
            .filter(AssociationLog.child_document_id == article1.document_id)
            .first()
        )
        assert assoc_wp_log is not None

        # Association to article created
        assoc_art = self.session.get(
            Association, (article1.document_id, self.article2.document_id)
        )
        assert assoc_art is not None

        assoc_art_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == article1.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert assoc_art_log is not None

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': QualityTypes.draft,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        article1 = self.session.get(Article, self.article1.document_id)
        assert article1.activities == ['hiking']

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': QualityTypes.draft,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
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
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        article1 = self.session.get(Article, self.article1.document_id)
        assert article1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': QualityTypes.draft,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        article1 = self.session.get(Article, self.article1.document_id)
        assert article1.get_locale('es').title == "Lac d'Annecy"

    # ──────────────────────────────────────────────────────────────
    # PUT — article-specific permission tests
    # ──────────────────────────────────────────────────────────────

    def test_put_change_collab_to_personal_as_non_author(self):
        """Non-moderator cannot change a collab article's
        type to personal."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'categories': ['technical'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                        'description': 'i am just changing the article type',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/articles/{self.article1.document_id}',
            json=body,
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Bad Request'

    def test_put_as_author(self):
        """Author of a personal article can update it."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article4.document_id,
                'version': self.article4.version,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'categories': ['technical'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.article4.locales[0].version,
                        'description': 'put should be allowed',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/articles/{self.article4.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        article4 = self.session.get(Article, self.article4.document_id)

        # version with lang 'en'
        versions = article4.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Another final EN title'

        archive_doc = version_en.document_archive
        assert archive_doc.activities == ['paragliding']
        assert archive_doc.categories == ['technical']
        assert archive_doc.article_type == 'personal'

    def test_put_as_non_author(self):
        """Non-author, non-moderator cannot update a
        personal article."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article4.document_id,
                'version': self.article4.version,
                'quality': QualityTypes.draft,
                'activities': ['rock_climbing'],
                'categories': ['technical'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.article4.locales[0].version,
                        'description': 'put should not be allowed',
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/articles/{self.article4.document_id}',
            json=body,
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Forbidden'

    # ──────────────────────────────────────────────────────────────
    # GET associations history
    # ──────────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        """GET /v2/associations-history?d={id} returns logs for article."""
        r = self.client.get(f'/v2/associations-history?d={self.article1.document_id}')
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
                child_id == self.article1.document_id
                or parent_id == self.article1.document_id
            )

    # ──────────────────────────────────────────────────────────────
    # GET detail — caching
    # ──────────────────────────────────────────────────────────────

    def test_get_caching(self):
        """GET /v2/articles/{id} populates the dogpile cache."""
        cache_key = get_cache_key(
            self.article1.document_id, None, document_type=ARTICLE_TYPE,
            db=self.session,
        )
        assert cache_document_detail.get(cache_key) == NO_VALUE

        r = self.client.get(f'/v2/articles/{self.article1.document_id}')
        assert r.status_code == 200

        assert cache_document_detail.get(cache_key) != NO_VALUE

    # ──────────────────────────────────────────────────────────────
    # GET version — ETag
    # ──────────────────────────────────────────────────────────────

    def test_get_version_etag(self):
        """GET version returns ETag; re-request with If-None-Match → 304."""
        assert self.article1_version is not None
        url = '/v2/articles/{}/{}/{}'.format(
            self.article1.document_id, 'en', self.article1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        etag = resp.headers.get('etag')
        assert etag is not None

        resp2 = self.client.get(url, headers={'If-None-Match': etag})
        assert resp2.status_code == 304

    # ──────────────────────────────────────────────────────────────
    # GET version — dogpile cache
    # ──────────────────────────────────────────────────────────────

    def test_get_version_caching(self):
        """GET version populates cache; fake value is served back."""
        assert self.article1_version is not None
        url = '/v2/articles/{}/{}/{}'.format(
            self.article1.document_id, 'en', self.article1_version.id
        )
        cache_key = '{}-{}'.format(
            get_cache_key(self.article1.document_id, 'en', ARTICLE_TYPE, db=self.session),
            self.article1_version.id,
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
