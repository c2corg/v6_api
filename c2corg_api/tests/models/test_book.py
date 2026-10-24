from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentLocale
from c2corg_api.tests import BaseTestCase


class TestBook(BaseTestCase):
    def test_to_archive(self):
        book = Book(
            document_id=1,
            activities=['hiking'],
            book_types=['biography'],
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='A', summary='C', description='abc'
                ),
                DocumentLocale(
                    id=3, lang='fr', title='B', summary='C', description='bcd'
                ),
            ],
        )

        book_archive = book.to_archive()

        assert book_archive.id is None
        assert book_archive.activities is not None
        assert book_archive.book_types is not None

        assert book_archive.document_id == book.document_id
        assert book_archive.activities == book.activities
        assert book_archive.book_types == book.book_types

        archive_locals = book.get_archive_locales()

        assert len(archive_locals) == 2
        locale = book.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
        assert locale_archive.description == locale.description
        assert locale_archive.type == locale.type
        assert locale_archive.summary == locale.summary
