from typing import List, Optional

from sqlalchemy import ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql.array import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_book import fields_book
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

BOOK_TYPE = document_types.BOOK_TYPE


class _BookMixin:
    author: Mapped[Optional[str]] = mapped_column(String(100))
    editor: Mapped[Optional[str]] = mapped_column(String(100))
    activities: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.activity_type)
    )
    url: Mapped[Optional[str]] = mapped_column(String(255))
    isbn: Mapped[Optional[str]] = mapped_column(String(17))
    book_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.book_type)
    )
    nb_pages: Mapped[Optional[int]] = mapped_column(SmallInteger)
    publication_date: Mapped[Optional[str]] = mapped_column(String(100))
    langs: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(2)))


attributes = [
    'author',
    'editor',
    'activities',
    'url',
    'isbn',
    'book_types',
    'nb_pages',
    'publication_date',
    'langs',
]


class Book(_BookMixin, Document):
    __tablename__ = 'books'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        book = ArchiveBook()
        super(Book, self)._to_archive(book)
        copy_attributes(self, book, attributes)

        return book

    def update(self, other):
        super(Book, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveBook(_BookMixin, ArchiveDocument):
    __tablename__ = 'books_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_book_attributes = list(schema_attributes)
schema_book_attributes.remove('geometry')

schema_book = build_field_spec(
    Book,
    includes=schema_book_attributes + attributes,
    locale_fields=schema_locale_attributes,
)

schema_listing_book = schema_book.restrict(fields_book.get('listing'))
