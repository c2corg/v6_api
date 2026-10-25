"""Schemas of the books."""

from c2corg_api.models.book import Book
from c2corg_api.models.common.fields_book import fields_book
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
)
from c2corg_api.schemas.types import Int, Seq, Str


class BookSchema(DocumentSchema):
    # no geometry: books are not on the map
    author: Str(100) = None
    editor: Str(100) = None
    # as with Colander, the items of activities and book_types are not checked
    # against their enum here
    activities: Seq(Str()) = None
    url: Str(255) = None
    isbn: Str(17) = None
    book_types: Seq(Str()) = None
    nb_pages: Int = None
    publication_date: Str(100) = None
    langs: Seq(Str()) = None


BookCreateSchema = create_schema(BookSchema, AssociationsSchema)
BookUpdateSchema = update_schema(BookCreateSchema)

book_schema = ModelSchema(Book, BookSchema, document_children())
book_listing_schema = book_schema.restrict(fields_book.get('listing'))
