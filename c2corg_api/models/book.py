from c2corg_api.models import schema, Base, enums
from c2corg_api.models.document import (
    ArchiveDocument, Document, schema_document_locale, schema_attributes)
from c2corg_api.models.schema_utils import get_update_schema, \
    restrict_schema, get_create_schema
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from sqlalchemy.dialects.postgresql.array import ARRAY
from c2corg_api.models.common.fields_book import fields_book
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    String,
    SmallInteger,
    ForeignKey
    )
from c2corg_api.models.common import document_types

BOOK_TYPE = document_types.BOOK_TYPE


class _BookMixin(object):
    author = Column(String(100))
    editor = Column(String(100))
    activities = Column(ArrayOfEnum(enums.activity_type))
    url = Column(String(255))
    isbn = Column(String(17))
    book_types = Column(ArrayOfEnum(enums.book_type))
    nb_pages = Column(SmallInteger)
    publication_date = Column(String(100))
    langs = Column(ARRAY(String(2)))


attributes = ['author', 'editor', 'activities', 'url', 'isbn',
              'book_types', 'nb_pages', 'publication_date', 'langs']


class Book(_BookMixin, Document):
    __tablename__ = 'books'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': Document.document_id == document_id
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

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


schema_book_locale = schema_document_locale
schema_book_attributes = list(schema_attributes)
schema_book_attributes.remove('geometry')

schema_book = SQLAlchemySchemaNode(
    Book,
    # whitelisted attributes
    includes=schema_book_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_book_locale]
        },
    })

schema_create_book = get_create_schema(schema_book)
schema_update_book = get_update_schema(schema_book)
schema_listing_book = restrict_schema(
    schema_book, fields_book.get('listing'))
