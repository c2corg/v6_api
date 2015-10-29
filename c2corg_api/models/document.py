from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    String,
    ForeignKey,
    Enum,
    func
    )
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry
from colander import MappingSchema, SchemaNode, String as ColanderString, null
from itertools import ifilter
import abc
import enum

from c2corg_api.models import Base, schema, DBSession
from c2corg_api.ext import colander_ext
from utils import copy_attributes

quality_types = [
    'stub',
    'medium',
    'correct',
    'good',
    'excellent'
    ]

UpdateType = enum.Enum(
    'UpdateType', 'FIGURES LANG GEOM')


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
    version = Column(Integer, nullable=False, server_default='1')
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

    locales = relationship('DocumentLocale')
    geometry = relationship('DocumentGeometry', uselist=False)

    available_cultures = None

    __mapper_args__ = {
            'version_id_col': _DocumentMixin.version
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

    def get_archive_geometry(self):
        return self.geometry.to_archive() if self.geometry else None

    def update(self, other):
        """Copies the attributes from `other` to this document.
        Also updates all locales.
        """
        copy_attributes(other, self, Document._ATTRIBUTES_WHITELISTED)

        for locale_in in other.locales:
            locale = self.get_locale(locale_in.culture)
            if locale:
                locale.update(locale_in)
                locale.document_id = self.document_id
            else:
                self.locales.append(locale_in)

        if other.geometry:
            if self.geometry:
                self.geometry.update(other.geometry)
            else:
                self.geometry = other.geometry
            self.geometry.document_id = self.document_id

    def get_versions(self):
        """Get the version hashs of this document and of all its locales.
        """
        return {
            'document': self.version,
            'locales': {
                locale.culture: locale.version for locale in self.locales
            },
            'geometry': self.geometry.version if self.geometry else None
        }

    def get_update_type(self, old_versions):
        """Get the update types (figures have changed, locales have
        changed, geometry has changed, or nothing has changed) and
        the languages that have changed.
        This is done by comparing the old version hashs (before flushing to
        the database) with the current hashs. Because SQLAlchemy automatically
        changes the hash, when something has changed, we can easily detect
        what has changed.
        """
        figures_equal = self.version == old_versions['document']
        geom_equal = self.geometry.version == old_versions['geometry'] if \
            self.geometry else old_versions['geometry'] is None

        changed_langs = []
        locale_versions = old_versions['locales']
        for locale in self.locales:
            locale_version = locale_versions.get(locale.culture)

            if not (locale_version and locale_version == locale.version):
                # new locale or locale has changed
                changed_langs.append(locale.culture)

        update_types = []
        if not figures_equal:
            update_types.append(UpdateType.FIGURES)
        if not geom_equal:
            update_types.append(UpdateType.GEOM)
        if changed_langs:
            update_types.append(UpdateType.LANG)

        return (update_types, changed_langs)

    def get_locale(self, culture):
        """Get the locale with the given culture or `None` if no locale
        is present.
        """
        return next(
            ifilter(lambda locale: locale.culture == culture, self.locales),
            None)


class ArchiveDocument(Base, _DocumentMixin):
    """
    The base class for the archive documents.
    """
    __tablename__ = 'documents_archives'
    id = Column(Integer, primary_key=True)

    @declared_attr
    def document_id(self):
        return Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=False)


# Locales for documents
class _DocumentLocaleMixin(object):
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, server_default='1')

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
    summary = Column(String(255))
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
        'version_id_col': _DocumentLocaleMixin.version
    }

    _ATTRIBUTES = [
        'document_id', 'version', 'culture', 'title', 'description',
        'summary'
    ]

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


class _DocumentGeometryMixin(object):
    version = Column(Integer, nullable=False)

    # TODO geom should be 3d?
    @declared_attr
    def geom(self):
        return Column(
            Geometry(geometry_type='GEOMETRY', srid=3857, management=True),
            info={
                'colanderalchemy': {
                    'typ': colander_ext.Geometry('GEOMETRY', srid=3857)
                }
            }
        )

    @declared_attr
    def geom_detail(self):
        return Column(
            Geometry(geometry_type='GEOMETRY', srid=3857, management=True),
            info={
                'colanderalchemy': {
                    'typ': colander_ext.Geometry('GEOMETRY', srid=3857)
                }
            }
        )


class DocumentGeometry(Base, _DocumentGeometryMixin):
    __tablename__ = 'documents_geometries'

    __colanderalchemy_config__ = {
        'missing': null
    }

    __mapper_args__ = {
        'version_id_col': _DocumentGeometryMixin.version
    }
    document_id = Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            primary_key=True)

    _ATTRIBUTES = \
        ['document_id', 'version', 'geom', 'geom_detail']

    def to_archive(self):
        geometry = ArchiveDocumentGeometry()
        copy_attributes(self, geometry, DocumentGeometry._ATTRIBUTES)
        return geometry

    def update(self, other):
        copy_attributes(other, self, DocumentGeometry._ATTRIBUTES)


class ArchiveDocumentGeometry(Base, _DocumentGeometryMixin):
    __tablename__ = 'documents_geometries_archives'

    id = Column(Integer, primary_key=True)
    document_id = Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=False)


schema_attributes = [
    'document_id', 'version', 'locales', 'geometry'
]
schema_locale_attributes = [
    'version', 'culture', 'title', 'description', 'summary'
]

geometry_schema_overrides = {
    # whitelisted attributes
    'includes': ['version', 'geom', 'geom_detail'],
    'overrides': {
        'version': {
            'missing': None
        }
    }
}


def get_update_schema(document_schema):
    """Create a Colander schema for the update view which contains an update
    message and the document.
    """
    class UpdateSchema(MappingSchema):
        message = SchemaNode(ColanderString(), missing='')
        document = document_schema.clone()

    return UpdateSchema()


def set_available_cultures(documents):
    """Load and set the available cultures for the given documents.
    """
    document_ids = [doc.document_id for doc in documents]
    documents_for_id = {doc.document_id: doc for doc in documents}

    # aggregate the cultures per document into an array
    culture_agg = func.array_agg(
        DocumentLocale.culture,
        type_=postgresql.ARRAY(String)).label('cultures')

    cultures_per_doc = DBSession.query(
        DocumentLocale.document_id, culture_agg). \
        filter(DocumentLocale.document_id.in_(document_ids)). \
        group_by(DocumentLocale.document_id). \
        all()

    for document_id, cultures in cultures_per_doc:
        document = documents_for_id.get(document_id)
        document.available_cultures = cultures
