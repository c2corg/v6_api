import enum

import abc

from c2corg_api.ext import colander_ext
from c2corg_api.models import Base, schema, DBSession, enums
from c2corg_api.models.utils import copy_attributes, extend_dict, wkb_to_shape
from c2corg_api.models.common import document_types
from c2corg_api.models.common.attributes import quality_types
from colander import null
from colanderalchemy.schema import SQLAlchemySchemaNode
from geoalchemy2 import Geometry, WKBElement
from pyramid.httpexceptions import HTTPInternalServerError
from shapely import wkt
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    String,
    ForeignKey,
    func
    )
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql.schema import UniqueConstraint

UpdateType = enum.Enum(
    'UpdateType', 'FIGURES LANG GEOM')

DOCUMENT_TYPE = document_types.DOCUMENT_TYPE


class Lang(Base):
    """The supported languages.
    """
    __tablename__ = 'langs'
    lang = Column(String(2), primary_key=True)


class _DocumentMixin(object):
    """
    Contains the attributes that are common for `Document` and
    `ArchiveDocument`.
    """
    version = Column(Integer, nullable=False, server_default='1')

    # a protected document can only be edited by moderators
    protected = Column(Boolean, nullable=False, server_default='false')

    @declared_attr
    def redirects_to(self):
        return Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=True)

    quality = Column(
        enums.quality_type, nullable=False, default=quality_types[1],
        server_default=quality_types[1])

    type = Column(String(1), index=True)
    __mapper_args__ = {
        'polymorphic_identity': DOCUMENT_TYPE,
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
    view_count = Column(Integer, nullable=False, server_default='0')

    locales = relationship('DocumentLocale')
    geometry = relationship('DocumentGeometry', uselist=False)

    available_langs = None

    __mapper_args__ = extend_dict({
        'version_id_col': _DocumentMixin.version
    }, _DocumentMixin.__mapper_args__)

    _ATTRIBUTES_WHITELISTED = \
        ['document_id', 'version', 'quality']

    _ATTRIBUTES = \
        _ATTRIBUTES_WHITELISTED + ['protected', 'redirects_to']

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
            locale = self.get_locale(locale_in.lang)
            if locale:
                locale.update(locale_in)
                locale.document_id = self.document_id
            else:
                self.locales.append(locale_in)

        if other.geometry:
            if self.geometry:
                if not self.geometry.almost_equals(other.geometry):
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
                locale.lang: locale.version for locale in self.locales
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
            locale_version = locale_versions.get(locale.lang)

            if not (locale_version and locale_version == locale.version):
                # new locale or locale has changed
                changed_langs.append(locale.lang)

        update_types = []
        if not figures_equal:
            update_types.append(UpdateType.FIGURES)
        if not geom_equal:
            update_types.append(UpdateType.GEOM)
        if changed_langs:
            update_types.append(UpdateType.LANG)

        return (update_types, changed_langs)

    def get_locale(self, lang):
        """Get the locale with the given lang or `None` if no locale
        is present.
        """
        return next(
            filter(lambda locale: locale.lang == lang, self.locales),
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

    __table_args__ = (
        # only one entry per document id and version
        UniqueConstraint(
            'version', 'document_id',
            name='uq_documents_archives_document_id_version'),
        Base.__table_args__
    )


# Locales for documents
class _DocumentLocaleMixin(object):
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, server_default='1')

    @declared_attr
    def document_id(self):
        return Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=False, index=True)

    @declared_attr
    def lang(self):
        return Column(
            String(2), ForeignKey(schema + '.langs.lang'),
            nullable=False)

    title = Column(String(150), nullable=False)
    summary = Column(String)
    description = Column(String)

    type = Column(String(1))
    __mapper_args__ = {
        'polymorphic_identity': DOCUMENT_TYPE,
        'polymorphic_on': type
    }


class DocumentLocale(Base, _DocumentLocaleMixin):
    __tablename__ = 'documents_locales'

    __mapper_args__ = {
        'polymorphic_identity': DOCUMENT_TYPE,
        'polymorphic_on': _DocumentLocaleMixin.type,
        'version_id_col': _DocumentLocaleMixin.version
    }

    _ATTRIBUTES = [
        'document_id', 'version', 'lang', 'title', 'description',
        'summary'
    ]

    topic_id = association_proxy('document_topic', 'topic_id')

    def to_archive(self):
        locale = ArchiveDocumentLocale()
        self._to_archive(locale)
        return locale

    def _to_archive(self, locale):
        copy_attributes(self, locale, DocumentLocale._ATTRIBUTES)
        return locale

    def update(self, other):
        copy_attributes(other, self, DocumentLocale._ATTRIBUTES)


class ArchiveDocumentLocale(Base, _DocumentLocaleMixin):
    __tablename__ = 'documents_locales_archives'

    __mapper_args__ = {
        'polymorphic_identity': DOCUMENT_TYPE,
        'polymorphic_on': _DocumentLocaleMixin.type
    }

    __table_args__ = (
        # only one entry per document id, version and lang
        UniqueConstraint(
            'version', 'document_id', 'lang',
            name='uq_documents_locales_archives_document_id_version_lang'),
        Base.__table_args__
    )


# `geomet` does not support EWKB, so load geometries as WKB
Geometry.as_binary = 'ST_AsBinary'


class _DocumentGeometryMixin(object):
    version = Column(Integer, nullable=False)

    @declared_attr
    def geom(self):
        return Column(
            Geometry(
                geometry_type='POINT', srid=3857, dimension=2,
                management=True,
                spatial_index=self.__name__ != 'ArchiveDocumentGeometry'),
            info={
                'colanderalchemy': {
                    'typ': colander_ext.Geometry(['POINT'], srid=3857)
                }
            }
        )

    @declared_attr
    def geom_detail(self):
        return Column(
            Geometry(
                geometry_type='GEOMETRY', srid=3857,
                management=True,
                use_typmod=False,
                spatial_index=self.__name__ != 'ArchiveDocumentGeometry'),
            info={
                'colanderalchemy': {
                    'typ': colander_ext.Geometry(['GEOMETRY'], srid=3857)
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

    def almost_equals(self, other):
        return self._almost_equals(self.geom, other.geom) and \
               self._almost_equals(self.geom_detail, other.geom_detail)

    def _almost_equals(self, geom, other_geom):
        if geom is None and other_geom is None:
            return True
        elif geom is not None and other_geom is None:
            return False
        elif geom is None and other_geom is not None:
            return False

        g1 = None
        proj1 = None
        if isinstance(geom, WKBElement):
            g1 = wkb_to_shape(geom)
            proj1 = geom.srid
        else:
            # WKT are used in the tests.
            split1 = str.split(geom, ';')
            proj1 = int(str.split(split1[0], '=')[1])
            str1 = split1[1]
            g1 = wkt.loads(str1)

        g2 = None
        proj2 = None
        if isinstance(other_geom, WKBElement):
            g2 = wkb_to_shape(other_geom)
            proj2 = other_geom.srid
        else:
            # WKT are used in the tests.
            split2 = str.split(other_geom, ';')
            proj2 = int(str.split(split2[0], '=')[1])
            str2 = split2[1]
            g2 = wkt.loads(str2)

        # https://github.com/Toblerity/Shapely/blob/
        # 8df2b1b718c89e7d644b246ab07ad3670d25aa6a/shapely/geometry/base.py#L673
        decimals = None
        if proj1 != proj2:
            # Should never occur
            raise HTTPInternalServerError('Incompatible projections')
        elif proj1 == 3857:
            decimals = -0.2  # +- 0.8m = 0.5 * 10^0.2
        elif proj1 == 4326:
            decimals = 7  # +- 1m
            # 5178564 740093 | gdaltransform -s_srs EPSG:3857 -t_srs EPSG:4326
            # 46.5198319099112 6.63349924965325 0
            # 5178565 740093 | gdaltransform -s_srs EPSG:3857 -t_srs EPSG:4326
            # 46.5198408930641 6.63349924965325 0
            # 46.5198408930641 - 46.5198319099112 = 0.0000089 -> 7 digits
        else:
            raise HTTPInternalServerError('Bad projection')

        return g1.almost_equals(g2, decimals)


DocumentGeometry.lon_lat = column_property(
    func.ST_AsGeoJSON(func.ST_Transform(DocumentGeometry.geom, 4326)),
    deferred=True)

DocumentGeometry.has_geom_detail = column_property(
    DocumentGeometry.geom_detail.isnot(None))


class ArchiveDocumentGeometry(Base, _DocumentGeometryMixin):
    __tablename__ = 'documents_geometries_archives'

    id = Column(Integer, primary_key=True)
    document_id = Column(
            Integer, ForeignKey(schema + '.documents.document_id'),
            nullable=False)

    __table_args__ = (
        # only one entry per document id and version
        UniqueConstraint(
            'version', 'document_id',
            name='uq_documents_geometries_archives_document_id_version_lang'),
        Base.__table_args__
    )


schema_attributes = [
    'document_id', 'version', 'locales', 'geometry', 'quality'
]
schema_locale_attributes = [
    'version', 'lang', 'title', 'description', 'summary'
]

schema_document_locale = SQLAlchemySchemaNode(
    DocumentLocale,
    # whitelisted attributes
    includes=schema_locale_attributes,
    overrides={
        'version': {
            'missing': None
        }
    })

geometry_schema_overrides = {
    # whitelisted attributes
    'includes': ['version', 'geom', 'geom_detail', 'has_geom_detail'],
    'overrides': {
        'version': {
            'missing': None
        }
    }
}


def get_geometry_schema_overrides(geometry_types):
    return {
        # whitelisted attributes
        'includes': ['version', 'geom', 'geom_detail', 'has_geom_detail'],
        'overrides': {
            'version': {
                'missing': None
            },
            'geom_detail': {
                'typ': colander_ext.Geometry(geometry_types, srid=3857)
            }
        }
    }


def get_available_langs(document_id):
    """Return the available languages (e.g. ['en', 'fr']) for a single
    document.
    """
    return DBSession. \
        query(
            func.array_agg(
                DocumentLocale.lang,
                type_=postgresql.ARRAY(String))). \
        filter(DocumentLocale.document_id == document_id). \
        group_by(DocumentLocale.document_id). \
        scalar()


def set_available_langs(documents, loaded=False):
    """Load and set the available langs for the given documents.
    """
    if len(documents) == 0:
        return

    if loaded:
        # all locales are already loaded, so simply set the attribute
        for document in documents:
            document.available_langs = [
                locale.lang for locale in document.locales]
    else:
        document_ids = [doc.document_id for doc in documents]
        documents_for_id = {doc.document_id: doc for doc in documents}

        # aggregate the langs per document into an array
        lang_agg = func.array_agg(
            DocumentLocale.lang,
            type_=postgresql.ARRAY(String)).label('langs')

        langs_per_doc = DBSession.query(
            DocumentLocale.document_id, lang_agg). \
            filter(DocumentLocale.document_id.in_(document_ids)). \
            group_by(DocumentLocale.document_id). \
            all()

        for document_id, langs in langs_per_doc:
            document = documents_for_id.get(document_id)
            document.available_langs = langs
