import pytest
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_version
from c2corg_api.models.article import ARTICLE_TYPE, ArchiveArticle, Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests import assert_required, auth_headers, send_json
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

ARTICLES = DocType(
    '/articles', ARTICLE_TYPE, Article, ArchiveArticle, ArchiveDocumentLocale
)


class TestArticleRest:
    @pytest.fixture(autouse=True)
    def _setup_test_article_rest(self, client, session, user_ids):
        self._add_test_data(session, user_ids)

    def test_get_collection(self, client, session):
        body = scenarios.get_collection(client, session, ARTICLES)
        doc = body['documents'][0]
        assert 'geometry' not in doc

        # the licence depends on the article type
        licenses = {
            doc['document_id']: doc['license']['id'] for doc in body['documents']
        }
        assert licenses[self.article1.document_id] == 'CC-BY-SA-3.0'
        assert licenses[self.article4.document_id] == 'CC-BY-NC-ND-3.0'

    def test_get_collection_paginated(self, client, session):
        client.get('/articles?offset=invalid', status=422)

        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, ARTICLES, {'offset': 0, 'limit': 0}
            ),
            [],
            4,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, ARTICLES, {'offset': 0, 'limit': 1}
            ),
            [self.article4.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, ARTICLES, {'offset': 0, 'limit': 2}
            ),
            [self.article4.document_id, self.article3.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(
                client, session, ARTICLES, {'offset': 1, 'limit': 2}
            ),
            [self.article3.document_id, self.article2.document_id],
            4,
        )

    def test_get_collection_lang(self, client):
        scenarios.get_collection_lang(client, ARTICLES)

    def test_get_collection_search(self, client, session):
        reset_search_index(session)

        scenarios.assert_results_equal(
            scenarios.get_collection_search(client, ARTICLES, {'l': 'en'}),
            [self.article4.document_id, self.article1.document_id],
            2,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection_search(client, ARTICLES, {'act': ['hiking']}),
            [
                self.article4.document_id,
                self.article3.document_id,
                self.article2.document_id,
                self.article1.document_id,
            ],
            4,
        )

    def test_get(self, client, user_ids):
        body = scenarios.get(
            client, ARTICLES, self.article1, title=self.locale_en.title
        )
        assert 'article' not in body
        assert 'geometry' not in body
        assert body.get('geometry') is None

        assert 'author' in body
        author = body.get('author')
        assert user_ids['contributor'] == author.get('user_id')

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

    def test_get_cooked(self, client):
        scenarios.get_cooked(client, ARTICLES, self.article1)

    def test_get_cooked_with_defaulting(self, client):
        scenarios.get_cooked_with_defaulting(client, ARTICLES, self.article1)

    def test_get_lang(self, client):
        scenarios.get_lang(client, ARTICLES, self.article1)

    def test_get_new_lang(self, client):
        scenarios.get_new_lang(client, ARTICLES, self.article1)

    def test_get_404(self, client):
        scenarios.get_404(client, ARTICLES)

    def test_get_version(self, client):
        scenarios.get_version(client, ARTICLES, self.article1, self.article1_version)

    def test_get_version_etag(self, client):
        url = (
            f'{ARTICLES.prefix}/{self.article1.document_id!s}/en'
            f'/{self.article1_version.id!s}'
        )
        response = client.get(url, status=200)

        # check that the ETag header is set
        headers = response.headers
        etag = headers.get('ETag')
        assert etag is not None

        # then request the document again with the etag
        headers = {'If-None-Match': etag}
        client.get(url, status=304, headers=headers)

    def test_get_version_caching(self, client):
        url = (
            f'{ARTICLES.prefix}/{self.article1.document_id!s}/en'
            f'/{self.article1_version.id!s}'
        )
        cache_key = '{}-{}'.format(
            get_cache_key(self.article1.document_id, 'en', ARTICLE_TYPE),
            self.article1_version.id,
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

    def test_get_caching(self, client):
        scenarios.get_caching(client, ARTICLES, self.article1)

    def test_get_info(self, client):
        body, locale = scenarios.get_info(client, ARTICLES, self.article1, 'en')
        assert locale.get('lang') == 'en'

    def test_get_info_best_lang(self, client):
        body, locale = scenarios.get_info(client, ARTICLES, self.article1, 'es')
        assert locale.get('lang') == 'fr'

    def test_get_info_404(self, client):
        scenarios.get_info_404(client, ARTICLES)

    def test_post_error(self, client):
        body = scenarios.post_error(client, ARTICLES, {}, user='moderator')
        errors = body.get('errors')
        assert len(errors) == 2
        assert_required(errors[0], 'locales')

    def test_post_missing_title(self, client):
        body_post = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'locales': [{'lang': 'en'}],
        }
        scenarios.post_missing_title(client, ARTICLES, body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self, client, session):
        body = {
            'article_type': 'collab',
            'protected': True,
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        scenarios.post_non_whitelisted_attribute(
            client, session, ARTICLES, body, user='moderator'
        )

    def test_post_missing_content_type(self, client):
        scenarios.post_missing_content_type(client, ARTICLES, {})

    def test_post_empty_assoc_in_new_c_document(self, client, session):
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

        body, doc = scenarios.post_success(
            client, session, ARTICLES, body, user='moderator'
        )

    def test_post_success(self, client, session):
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
        body, doc = scenarios.post_success(
            client, session, ARTICLES, body, user='moderator'
        )
        version = doc.versions[0]

        archive_article = version.document_archive
        assert archive_article.categories == ['site_info']
        assert archive_article.activities == ['hiking']
        assert archive_article.article_type == 'collab'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        # check if geometry is not stored in database afterwards
        assert doc.geometry is None

        # check that a link to the associated waypoint is created
        association_wp = session.get(
            Association, (self.waypoint2.document_id, doc.document_id)
        )
        assert association_wp is not None

        association_wp_log = (
            session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint2.document_id)
            .filter(AssociationLog.child_document_id == doc.document_id)
            .first()
        )
        assert association_wp_log is not None

        # check that a link to the associated article is created
        association_main_art = session.get(
            Association, (doc.document_id, self.article2.document_id)
        )
        assert association_main_art is not None

        association_main_art_log = (
            session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert association_main_art_log is not None

    def test_put_wrong_document_id(self, client):
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
        scenarios.put_wrong_document_id(client, ARTICLES, body, user='moderator')

    def test_put_wrong_document_version(self, client):
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
        scenarios.put_wrong_version(
            client, ARTICLES, body, self.article1.document_id, user='moderator'
        )

    def test_put_wrong_locale_version(self, client):
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
        scenarios.put_wrong_version(
            client, ARTICLES, body, self.article1.document_id, user='moderator'
        )

    def test_put_wrong_ids(self, client):
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
        scenarios.put_wrong_ids(
            client, ARTICLES, body, self.article1.document_id, user='moderator'
        )

    def test_put_no_document(self, client):
        scenarios.put_no_document(
            client, ARTICLES, self.article1.document_id, user='moderator'
        )

    def test_put_success_all(self, client, session):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
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
        (body, article1) = scenarios.put_success_all(
            client,
            session,
            ARTICLES,
            body,
            self.article1,
            user='moderator',
            cache_version=3,
            locale_fr=self.locale_fr,
        )

        assert article1.activities == ['hiking']
        locale_en = article1.get_locale('en')
        assert locale_en.title == 'New title'

        # version with lang 'en'
        versions = article1.versions
        version_en = scenarios.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'New title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.categories == ['site_info']
        assert archive_document_en.activities == ['hiking']
        assert archive_document_en.article_type == 'personal'

        # version with lang 'fr'
        version_fr = scenarios.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        assert archive_locale.title == "Lac d'Annecy"

        # check if geometry is not stored in database afterwards
        assert article1.geometry is None
        # check that a link to the associated waypoint is created
        association_wp = session.get(
            Association, (self.waypoint2.document_id, article1.document_id)
        )
        assert association_wp is not None

        association_wp_log = (
            session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint2.document_id)
            .filter(AssociationLog.child_document_id == article1.document_id)
            .first()
        )
        assert association_wp_log is not None

        # check that a link to the associated article is created
        association_main_art = session.get(
            Association, (article1.document_id, self.article2.document_id)
        )
        assert association_main_art is not None

        association_main_art_log = (
            session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == article1.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert association_main_art_log is not None

    def test_put_success_figures_only(self, client, session):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
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
        (body, article1) = scenarios.put_success_figures_only(
            client, session, ARTICLES, body, self.article1, user='moderator'
        )

        assert article1.activities == ['hiking']

    def test_put_success_lang_only(self, client, session):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
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
        (body, article1) = scenarios.put_success_lang_only(
            client, session, ARTICLES, body, self.article1, user='moderator'
        )

        assert article1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self, client, session):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        (body, article1) = scenarios.put_success_new_lang(
            client, session, ARTICLES, body, self.article1, user='moderator'
        )

        assert article1.get_locale('es').title == "Lac d'Annecy"

    def test_put_change_collab_to_personal_as_non_author(self, client):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
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

        headers = auth_headers(username='contributor2')
        response = send_json(
            client,
            'put',
            ARTICLES.prefix + '/' + str(self.article1.document_id),
            body,
            headers=headers,
            status=400,
        )

        body = response.json
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Bad Request'

    def test_put_as_author(self, client, session):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article4.document_id,
                'version': self.article4.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],
                'categories': ['technical'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                        'description': 'put should be allowed',
                    }
                ],
            },
        }

        (body, article4) = scenarios.put_success_all(
            client,
            session,
            ARTICLES,
            body,
            self.article4,
            user='contributor',
            cache_version=2,
            locale_fr=self.locale_fr,
        )

        # version with lang 'en'
        versions = article4.versions
        version_en = scenarios.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Another final EN title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.activities == ['paragliding']
        assert archive_document_en.categories == ['technical']
        assert archive_document_en.article_type == 'personal'

    def test_put_as_non_author(self, client):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.article4.document_id,
                'version': self.article4.version,
                'quality': quality_types[1],
                'activities': ['rock_climbing'],
                'categories': ['technical'],
                'article_type': 'personal',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                        'description': 'put should not be allowed',
                    }
                ],
            },
        }

        headers = auth_headers(username='contributor2')
        response = send_json(
            client,
            'put',
            ARTICLES.prefix + '/' + str(self.article4.document_id),
            body,
            headers=headers,
            status=403,
        )

        body = response.json
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Forbidden'

    def test_get_associations_history(self, client):
        scenarios.get_association_logs(client, self.article1)

    def _add_test_data(self, session, user_ids):
        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.locale_en = DocumentLocale(lang='en', title="Lac d'Annecy")
        self.locale_fr = DocumentLocale(lang='fr', title="Lac d'Annecy")

        self.article1.locales.append(self.locale_en)
        self.article1.locales.append(self.locale_fr)

        session.add(self.article1)
        session.flush()

        user_id = user_ids['contributor']
        create_new_version(self.article1, user_id)
        self.article1_version = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.article1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        session.add(self.article2)
        self.article3 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        session.add(self.article3)
        self.article4 = Article(
            categories=['site_info'], activities=['hiking'], article_type='personal'
        )
        self.article4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.article4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        session.add(self.article4)
        session.flush()

        create_new_version(self.article4, user_id)
        self.article4_version = (
            session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.article4.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        session.add(self.waypoint2)
        session.flush()

        scenarios.add_association(
            session,
            Association.create(
                parent_document=self.article1, child_document=self.article4
            ),
            user_id,
        )
        scenarios.add_association(
            session,
            Association.create(
                parent_document=self.article3, child_document=self.article1
            ),
            user_id,
        )
        session.flush()
