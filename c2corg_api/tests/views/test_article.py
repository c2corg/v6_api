from c2corg_api.caching import cache_document_version
from c2corg_api.models.article import ArchiveArticle, Article, ARTICLE_TYPE
from c2corg_api.models.association import AssociationLog, Association
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests.search import reset_search_index

from c2corg_api.models.document import (
    ArchiveDocumentLocale, DocumentLocale, DocumentGeometry)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest
from c2corg_api.models.common.attributes import quality_types
from dogpile.cache.api import NO_VALUE


class TestArticleRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/articles", ARTICLE_TYPE, Article, ArchiveArticle,
            ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertNotIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.app.get("/articles?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.article4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.article4.document_id, self.article3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.article3.document_id, self.article2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.article4.document_id, self.article1.document_id], 2)

        self.assertResultsEqual(
            self.get_collection_search({'act': ['hiking']}),
            [self.article4.document_id, self.article3.document_id,
             self.article2.document_id, self.article1.document_id], 4)

    def test_get(self):
        body = self.get(self.article1)
        self.assertNotIn('article', body)
        self.assertNotIn('geometry', body)
        self.assertIsNone(body.get('geometry'))

        self.assertIn('author', body)
        author = body.get('author')
        self.assertEqual(
            self.global_userids['contributor'], author.get('user_id'))

        associations = body['associations']
        self.assertIn('articles', associations)
        self.assertIn('books', associations)
        self.assertIn('images', associations)
        self.assertIn('waypoints', associations)
        self.assertIn('routes', associations)
        self.assertIn('xreports', associations)
        self.assertIn('users', associations)

        linked_articles = associations.get('articles')
        self.assertEqual(len(linked_articles), 2)

    def test_get_cooked(self):
        self.get_cooked(self.article1)

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.article1)

    def test_get_lang(self):
        self.get_lang(self.article1)

    def test_get_new_lang(self):
        self.get_new_lang(self.article1)

    def test_get_404(self):
        self.get_404()

    def test_get_version(self):
        self.get_version(self.article1, self.article1_version)

    def test_get_version_etag(self):
        url = '{0}/{1}/en/{2}'.format(
                self._prefix, str(self.article1.document_id),
                str(self.article1_version.id))
        response = self.app.get(url, status=200)

        # check that the ETag header is set
        headers = response.headers
        etag = headers.get('ETag')
        self.assertIsNotNone(etag)

        # then request the document again with the etag
        headers = {
            'If-None-Match': etag
        }
        self.app.get(url, status=304, headers=headers)

    def test_get_version_caching(self):
        url = '{0}/{1}/en/{2}'.format(
                self._prefix, str(self.article1.document_id),
                str(self.article1_version.id))
        cache_key = '{0}-{1}'.format(
            get_cache_key(self.article1.document_id, 'en', ARTICLE_TYPE),
            self.article1_version.id)

        cache_value = cache_document_version.get(cache_key)
        self.assertEqual(cache_value, NO_VALUE)

        # check that the response is cached
        self.app.get(url, status=200)

        cache_value = cache_document_version.get(cache_key)
        self.assertNotEqual(cache_value, NO_VALUE)

        # check that values are returned from the cache
        fake_cache_value = {'document': 'fake doc'}
        cache_document_version.set(cache_key, fake_cache_value)

        response = self.app.get(url, status=200)
        body = response.json
        self.assertEqual(body, fake_cache_value)

    def test_get_caching(self):
        self.get_caching(self.article1)

    def test_get_info(self):
        body, locale = self.get_info(self.article1, 'en')
        self.assertEqual(locale.get('lang'), 'en')

    def test_get_info_best_lang(self):
        body, locale = self.get_info(self.article1, 'es')
        self.assertEqual(locale.get('lang'), 'fr')

    def test_get_info_404(self):
        self.get_info_404()

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales')

    def test_post_missing_title(self):
        body_post = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'locales': [
                {'lang': 'en'}
            ]
        }
        self.post_missing_title(body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'article_type': 'collab',
            'protected': True,
            'locales': [
                {'lang': 'en', 'title': 'Lac d\'Annecy'}
            ]
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

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
                 'areas': []
            },
            'locales': [{
                'lang': 'en',
                'title': 'new testing article',
                'description': 'some description',
                'summary': 'some summary'
            }]
        }

        body, doc = self.post_success(body, user='moderator')

    def test_post_success(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'associations': {
                'waypoints': [
                    {'document_id': self.waypoint2.document_id}
                ],
                'articles': [
                    {'document_id': self.article2.document_id}
                ]
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom':
                    '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Lac d\'Annecy'}
            ]
        }
        body, doc = self.post_success(body, user='moderator')
        version = doc.versions[0]

        archive_article = version.document_archive
        self.assertEqual(archive_article.categories, ['site_info'])
        self.assertEqual(archive_article.activities, ['hiking'])
        self.assertEqual(archive_article.article_type, 'collab')

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        # check if geometry is not stored in database afterwards
        self.assertIsNone(doc.geometry)

        # check that a link to the associated waypoint is created
        association_wp = self.session.query(Association).get(
            (self.waypoint2.document_id, doc.document_id))
        self.assertIsNotNone(association_wp)

        association_wp_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint2.document_id). \
            filter(AssociationLog.child_document_id ==
                   doc.document_id). \
            first()
        self.assertIsNotNone(association_wp_log)

        # check that a link to the associated article is created
        association_main_art = self.session.query(Association).get(
            (doc.document_id, self.article2.document_id))
        self.assertIsNotNone(association_main_art)

        association_main_art_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   doc.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.article2.document_id). \
            first()
        self.assertIsNotNone(association_main_art_log)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': -9999,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(
            body, self.article1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(
            body, self.article1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.article1.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.article1.document_id, user='moderator')

    def test_put_success_all(self):
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
                    'waypoints': [
                        {'document_id': self.waypoint2.document_id}
                    ],
                    'articles': [
                        {'document_id': self.article2.document_id}
                    ],
                    'images': []
                },
                'geometry': {
                    'geom':
                        '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, article1) = self.put_success_all(
            body, self.article1, user='moderator', cache_version=3)

        self.assertEqual(article1.activities, ['hiking'])
        locale_en = article1.get_locale('en')
        self.assertEqual(locale_en.title, 'New title')

        # version with lang 'en'
        versions = article1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'New title')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.categories, ['site_info'])
        self.assertEqual(archive_document_en.activities, ['hiking'])
        self.assertEqual(archive_document_en.article_type, 'personal')

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        # check if geometry is not stored in database afterwards
        self.assertIsNone(article1.geometry)
        # check that a link to the associated waypoint is created
        association_wp = self.session.query(Association).get(
            (self.waypoint2.document_id, article1.document_id))
        self.assertIsNotNone(association_wp)

        association_wp_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint2.document_id). \
            filter(AssociationLog.child_document_id ==
                   article1.document_id). \
            first()
        self.assertIsNotNone(association_wp_log)

        # check that a link to the associated article is created
        association_main_art = self.session.query(Association).get(
            (article1.document_id, self.article2.document_id))
        self.assertIsNotNone(association_main_art)

        association_main_art_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   article1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.article2.document_id). \
            first()
        self.assertIsNotNone(association_main_art_log)

    def test_put_success_figures_only(self):
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
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, article1) = self.put_success_figures_only(
            body, self.article1, user='moderator')

        self.assertEqual(article1.activities, ['hiking'])

    def test_put_success_lang_only(self):
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
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, article1) = self.put_success_lang_only(
            body, self.article1, user='moderator')

        self.assertEqual(article1.get_locale('en').title, 'New title')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.article1.document_id,
                'version': self.article1.version,
                'quality': quality_types[1],
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [
                    {'lang': 'es', 'title': 'Lac d\'Annecy'}
                ]
            }
        }
        (body, article1) = self.put_success_new_lang(
            body, self.article1, user='moderator')

        self.assertEqual(article1.get_locale('es').title, 'Lac d\'Annecy')

    def test_put_change_collab_to_personal_as_non_author(self):
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
                    {'lang': 'en', 'title': 'Another final EN title',
                     'version': self.locale_en.version,
                     'description': 'i am just changing the article type'}
                ]
            }
        }

        headers = self.add_authorization_header(username='contributor2')
        response = self.app_put_json(
            self._prefix + '/' + str(self.article1.document_id), body,
            headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(len(body['errors']), 1)
        self.assertEqual(body['errors'][0]['name'], 'Bad Request')

    def test_put_as_author(self):
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
                    {'lang': 'en', 'title': 'Another final EN title',
                     'version': self.locale_en.version,
                     'description': 'put should be allowed'}
                ]
            }
        }

        (body, article4) = self.put_success_all(
            body, self.article4, user='contributor', cache_version=2)

        # version with lang 'en'
        versions = article4.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Another final EN title')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['paragliding'])
        self.assertEqual(archive_document_en.categories, ['technical'])
        self.assertEqual(archive_document_en.article_type, 'personal')

    def test_put_as_non_author(self):
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
                    {'lang': 'en', 'title': 'Another final EN title',
                     'version': self.locale_en.version,
                     'description': 'put should not be allowed'}
                ]
            }
        }

        headers = self.add_authorization_header(username='contributor2')
        response = self.app_put_json(
            self._prefix + '/' + str(self.article4.document_id), body,
            headers=headers,
            status=403)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(len(body['errors']), 1)
        self.assertEqual(body['errors'][0]['name'], 'Forbidden')

    def test_get_associations_history(self):
        self._get_association_logs(self.article1)

    def _add_test_data(self):
        self.article1 = Article(categories=['site_info'],
                                activities=['hiking'],
                                article_type='collab')
        self.locale_en = DocumentLocale(lang='en', title='Lac d\'Annecy')
        self.locale_fr = DocumentLocale(lang='fr', title='Lac d\'Annecy')

        self.article1.locales.append(self.locale_en)
        self.article1.locales.append(self.locale_fr)

        self.session.add(self.article1)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.article1, user_id)
        self.article1_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.article1.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='collab')
        self.session.add(self.article2)
        self.article3 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='collab')
        self.session.add(self.article3)
        self.article4 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='personal')
        self.article4.locales.append(DocumentLocale(
            lang='en', title='Lac d\'Annecy'))
        self.article4.locales.append(DocumentLocale(
            lang='fr', title='Lac d\'Annecy'))
        self.session.add(self.article4)
        self.session.flush()

        DocumentRest.create_new_version(self.article4, user_id)
        self.article4_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.article4.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor', elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)')
            )
        self.session.add(self.waypoint2)
        self.session.flush()

        self._add_association(Association.create(
            parent_document=self.article1,
            child_document=self.article4), user_id)
        self._add_association(Association.create(
            parent_document=self.article3,
            child_document=self.article1), user_id)
        self.session.flush()
