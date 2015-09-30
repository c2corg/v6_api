from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    String,
    ForeignKey,
    Enum
    )
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship
import abc
import uuid

from c2corg_api.models import Base, schema
from utils import copy_attributes

quality_types = [
    'stub',
    'medium',
    'correct',
    'good',
    'excellent'
    ]


class Culture(Base):
    """The supported languages.
    """
    __tablename__ = 'cultures'
    culture = Column(String(2), primary_key=True)


class _DocumentMixin(object):
    """
    Contains the attributes that are common for `Document` and
    `ArchiveDocument`.
    """
    version = Column(String(32), nullable=False)
    # move to metadata?
    protected = Column(Boolean)
    redirects_to = Column(Integer)
    quality = Column(
        Enum(name='quality_type', inherit_schema=True, *quality_types))

    type = Column(String(1))
    __mapper_args__ = {
        'polymorphic_identity': 'd',
        'polymorphic_on': type
    }


class Document(Base, _DocumentMixin):
    """
    The base class from which all document types will inherit. For each child
    class (e.g. waypoint, route, ...) a separate table will be created, which
    is linked to the base table via "joined table inheritance".

    This table contains the current version of a document.
    """
    __tablename__ = 'documents'
    document_id = Column(Integer, primary_key=True)

    # TODO constraint that there is at least one locale
    locales = relationship('DocumentLocale')

    __mapper_args__ = {
            'version_id_col': _DocumentMixin.version,
            'version_id_generator': lambda version: uuid.uuid4().hex
    }

    _ATTRIBUTES_WHITELISTED = \
        ['document_id', 'version']

    _ATTRIBUTES = \
        _ATTRIBUTES_WHITELISTED + ['protected', 'redirects_to', 'quality']

    @abc.abstractmethod
    def to_archive(self):
        """Create an `Archive*` instance with the same attributes.
        This method is supposed to be implemented by child classes.
        """
        return

    def _to_archive(self, doc):
        """Copy the attributes of this document into a passed in
        `Archive*` instance.
        """
        copy_attributes(self, doc, Document._ATTRIBUTES)
        return doc

    def get_archive_locales(self):
        return [locale.to_archive() for locale in self.locales]

    def update(self, other):
        copy_attributes(other, self, Document._ATTRIBUTES_WHITELISTED)

    def get_locale(self, culture):
        """Get the locale with the given culture or `None` if no locale
        is present.
        """
        l = [locale for locale in self.locales if locale.culture == culture]
        if l:
            return l[0]
        else:
            return None


class ArchiveDocument(Base, _DocumentMixin):
    """
    The base class for the archive documents.
    """
    __tablename__ = 'documents_archives'
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, nullable=False)  # TODO as fk


# Locales for documents
class _DocumentLocaleMixin(object):
    id = Column(Integer, primary_key=True)
    version = Column(String(32))

    @declared_attr
    def document_id(self):
        return Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=False)

    @declared_attr
    def culture(self):
        return Column(
            String(2), ForeignKey(schema + '.cultures.culture'),
            nullable=False)

    title = Column(String(150), nullable=False)
    description = Column(String)

    type = Column(String(1))
    __mapper_args__ = {
        'polymorphic_identity': 'd',
        'polymorphic_on': type
    }


class DocumentLocale(Base, _DocumentLocaleMixin):
    __tablename__ = 'documents_locales'

    __mapper_args__ = {
        'polymorphic_identity': 'd',
        'polymorphic_on': _DocumentLocaleMixin.type,
        'version_id_col': _DocumentLocaleMixin.version,
        'version_id_generator': lambda version: uuid.uuid4().hex
    }

    _ATTRIBUTES = ['document_id', 'version', 'culture', 'title', 'description']

    def to_archive(self, locale):
        copy_attributes(self, locale, DocumentLocale._ATTRIBUTES)
        return locale

    def update(self, other):
        copy_attributes(other, self, DocumentLocale._ATTRIBUTES)


class ArchiveDocumentLocale(Base, _DocumentLocaleMixin):
    __tablename__ = 'documents_locales_archives'

    __mapper_args__ = {
        'polymorphic_identity': 'd',
        'polymorphic_on': _DocumentLocaleMixin.type
    }
