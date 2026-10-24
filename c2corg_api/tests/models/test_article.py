from c2corg_api.models.article import Article
from c2corg_api.models.document import DocumentLocale
from c2corg_api.tests import BaseTestCase


class TestArticle(BaseTestCase):
    def test_to_archive(self):
        article = Article(
            document_id=1,
            categories=['expeditions'],
            activities=['hiking'],
            article_type='personal',
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='A', summary='C', description='abc'
                ),
                DocumentLocale(
                    id=3, lang='fr', title='B', summary='C', description='bcd'
                ),
            ],
        )

        article_archive = article.to_archive()

        assert article_archive.id is None
        assert article_archive.activities is not None
        assert article_archive.article_type is not None

        assert article_archive.document_id == article.document_id
        assert article_archive.activities == article.activities
        assert article_archive.article_type == article.article_type
        assert article_archive.categories == article.categories

        archive_locals = article.get_archive_locales()

        assert len(archive_locals) == 2
        locale = article.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
        assert locale_archive.description == locale.description
        assert locale_archive.type == locale.type
        assert locale_archive.summary == locale.summary
