from c2corg_api.models.book import (
    Book,
    schema_book,
    schema_create_book,
    schema_listing_book,
    schema_update_book,
)
from c2corg_api.models.document import DocumentLocale
from c2corg_api.schemas.book import (
    BookCreateSchema,
    BookUpdateSchema,
    book_listing_schema,
    book_schema,
)
from c2corg_api.tests.schemas.parity import assert_parity
from c2corg_api.views import serialize


def _book():
    return Book(
        document_id=1,
        version=2,
        quality='fine',
        author='Author',
        activities=['hiking'],
        nb_pages=150,
        locales=[DocumentLocale(lang='en', title='Title', version=1, summary='s')],
    )


class TestBookSchemas:
    def test_create(self):
        assert_parity(schema_create_book, BookCreateSchema)

    def test_update(self):
        assert_parity(schema_update_book, BookUpdateSchema)

    def test_dictify(self):
        book = _book()
        assert serialize(book_schema.dictify(book)) == serialize(
            schema_book.dictify(book)
        )

    def test_listing_dictify(self):
        book = _book()
        assert serialize(book_listing_schema.dictify(book)) == serialize(
            schema_listing_book.dictify(book)
        )

    def test_objectify(self):
        data = schema_create_book.deserialize(
            {
                'author': 'Author',
                'nb_pages': 10,
                'locales': [{'lang': 'en', 'title': 'Title'}],
            }
        )
        expected = schema_book.objectify(data)
        actual = book_schema.objectify(data)
        assert serialize(book_schema.dictify(actual)) == serialize(
            schema_book.dictify(expected)
        )
