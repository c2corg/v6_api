from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.article import Article

from c2corg_api.tests import BaseTestCase


class TestArticle(BaseTestCase):

    def test_to_archive(self):
        article = Article(
            document_id=1, categories=['expeditions'], activities=['hiking'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='A', summary='C',
                    description='abc'),
                DocumentLocale(
                    id=3, lang='fr', title='B', summary='C',
                    description='bcd'),
            ]
        )

        article_archive = article.to_archive()

        self.assertIsNone(article_archive.id)
        self.assertIsNotNone(article_archive.activities)
        self.assertIsNotNone(article_archive.article_type)

        self.assertEqual(article_archive.document_id, article.document_id)
        self.assertEqual(article_archive.activities, article.activities)
        self.assertEqual(article_archive.article_type, article.article_type)
        self.assertEqual(article_archive.categories, article.categories)

        archive_locals = article.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = article.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
        self.assertEqual(locale_archive.type, locale.type)
        self.assertEqual(locale_archive.summary, locale.summary)
