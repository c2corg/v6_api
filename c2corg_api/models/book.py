from sqlalchemy import Column, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql.array import ARRAY

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
)
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

BOOK_TYPE = document_types.BOOK_TYPE


class _BookMixin:
    author = Column(String(100))
    editor = Column(String(100))
    activities = Column(ArrayOfEnum(enums.activity_type))
    url = Column(String(255))
    isbn = Column(String(17))
    book_types = Column(ArrayOfEnum(enums.book_type))
    nb_pages = Column(SmallInteger)
    publication_date = Column(String(100))
    langs = Column(ARRAY(String(2)))


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

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        book = ArchiveBook()
        super()._to_archive(book)
        copy_attributes(self, book, attributes)

        return book

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveBook(_BookMixin, ArchiveDocument):
    __tablename__ = 'books_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': BOOK_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__
