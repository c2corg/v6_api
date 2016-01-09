from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    ForeignKey,
    Enum
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    get_update_schema, geometry_schema_overrides)
from c2corg_common.attributes import activities

IMAGE_TYPE = 'i'


class _ImageMixin(object):
    activities = Column(
        Enum(name='activities', inherit_schema=True, *activities),
        nullable=False)

    height = Column(SmallInteger)

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE
    }


class Image(_ImageMixin, Document):
    """
    """
    __tablename__ = 'images'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    _ATTRIBUTES = ['activities', 'height']

    def to_archive(self):
        image = ArchiveImage()
        super(Image, self)._to_archive(image)
        copy_attributes(self, image, Image._ATTRIBUTES)

        return image

    def update(self, other):
        super(Image, self).update(other)
        copy_attributes(other, self, Image._ATTRIBUTES)


class ArchiveImage(_ImageMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'images_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)


class _ImageLocaleMixin(object):

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE
    }


class ImageLocale(_ImageLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'images_locales'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    _ATTRIBUTES = []

    def to_archive(self):
        locale = ArchiveImageLocale()
        super(ImageLocale, self).to_archive(locale)
        copy_attributes(self, locale, ImageLocale._ATTRIBUTES)

        return locale

    def update(self, other):
        super(ImageLocale, self).update(other)
        copy_attributes(other, self, ImageLocale._ATTRIBUTES)


class ArchiveImageLocale(_ImageLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'images_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)


schema_image_locale = SQLAlchemySchemaNode(
    ImageLocale,
    # whitelisted attributes
    includes=['version', 'culture', 'title', 'description'],
    overrides={
        'version': {
            'missing': None
        }
    })

schema_image = SQLAlchemySchemaNode(
    Image,
    # whitelisted attributes
    includes=[
        'document_id', 'version', 'activities', 'height', 'locales',
        'geometry'],
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_image_locale]
        },
        'geometry': geometry_schema_overrides
    })

schema_update_image = get_update_schema(schema_image)
