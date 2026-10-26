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
from c2corg_api.tests.schemas.parity import assert_document_type_parity


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


def test_book_parity():
    assert_document_type_parity(
        (schema_create_book, schema_update_book, schema_book, schema_listing_book),
        (BookCreateSchema, BookUpdateSchema, book_schema, book_listing_schema),
        _book(),
    )
