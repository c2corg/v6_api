from c2corg_api.models import schema, Base, enums
from c2corg_api.models.document import (
    ArchiveDocument, Document,
    schema_attributes, schema_locale_attributes)
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from sqlalchemy.dialects.postgresql.array import ARRAY
from c2corg_api.models.common.fields_book import fields_book
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


schema_book_attributes = list(schema_attributes)
schema_book_attributes.remove('geometry')

schema_book = build_field_spec(
    Book,
    includes=schema_book_attributes + attributes,
    locale_fields=schema_locale_attributes,
)

schema_listing_book = schema_book.restrict(
    fields_book.get('listing'))


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    get_create_schema as pydantic_create_schema,
    DocumentLocaleSchema,
    AssociationsSchema,
    _DuplicateLocalesMixin,
)
from c2corg_api.models.document import schema_attributes  # noqa: E402
from typing import List, Optional  # noqa: E402

# Books don't have geometry – exclude it from the schema_attributes
_book_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_BookDocBase = schema_from_sa_model(
    Book,
    name='_BookDocBase',
    includes=_book_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
    },
)


class BookDocumentSchema(
    _DuplicateLocalesMixin, _BookDocBase,
):
    """Full book document for create/update requests."""
    locales: Optional[List[DocumentLocaleSchema]] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateBookSchema = pydantic_create_schema(
    BookDocumentSchema,
    name='CreateBookSchema',
)

UpdateBookSchema = pydantic_update_schema(
    BookDocumentSchema,
    name='UpdateBookSchema',
)
