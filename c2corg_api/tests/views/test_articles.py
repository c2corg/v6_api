from c2corg_api.models.article import ArchiveArticle, Article, ARTICLE_TYPE
from c2corg_api.tests.search import reset_search_index

from c2corg_api.models.document import (
    ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest
from c2corg_common.attributes import quality_types


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

    def test_get_lang(self):
        self.get_lang(self.article1)

    def test_get_new_lang(self):
        self.get_new_lang(self.article1)

    def test_get_404(self):
        self.get_404()

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales')
        # self.assertCorniceRequired(errors[1], 'geometry')

    def test_post_missing_title(self):
        body_post = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'locales': [
                {'lang': 'en'}
            ]
        }
        body = self.post_missing_title(body_post, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales.0.title')
        self.assertCorniceRequired(errors[1], 'locales')

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

    def test_post_success(self):
        body = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
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

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
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
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, article1) = self.put_success_all(
            body, self.article1, user='moderator')

        self.assertEquals(article1.activities, ['hiking'])
        locale_en = article1.get_locale('en')
        self.assertEquals(locale_en.title, 'New title')

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

        self.assertEquals(article1.activities, ['hiking'])

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

        self.assertEquals(article1.get_locale('en').title, 'New title')

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

        self.assertEquals(article1.get_locale('es').title, 'Lac d\'Annecy')

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
            article_type='collab')
        self.article4.locales.append(DocumentLocale(
            lang='en', title='Lac d\'Annecy'))
        self.article4.locales.append(DocumentLocale(
            lang='fr', title='Lac d\'Annecy'))
        self.session.add(self.article4)
        self.session.flush()
