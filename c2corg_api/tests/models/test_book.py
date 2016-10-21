from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.book import Book

from c2corg_api.tests import BaseTestCase


class TestBook(BaseTestCase):

    def test_to_archive(self):
        book = Book(
            document_id=1,
            activities=['hiking'],
            book_types=['biography'],
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='A', summary='C',
                    description='abc'),
                DocumentLocale(
                    id=3, lang='fr', title='B', summary='C',
                    description='bcd'),
            ]
        )

        book_archive = book.to_archive()

        self.assertIsNone(book_archive.id)
        self.assertIsNotNone(book_archive.activities)
        self.assertIsNotNone(book_archive.book_types)

        self.assertEqual(book_archive.document_id, book.document_id)
        self.assertEqual(book_archive.activities, book.activities)
        self.assertEqual(book_archive.book_types, book.book_types)

        archive_locals = book.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = book.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
        self.assertEqual(locale_archive.type, locale.type)
        self.assertEqual(locale_archive.summary, locale.summary)
