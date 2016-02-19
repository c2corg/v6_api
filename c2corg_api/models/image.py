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
    ArchiveDocument, Document, get_update_schema, geometry_schema_overrides,
    schema_document_locale, schema_attributes)
from c2corg_common.attributes import activities

IMAGE_TYPE = 'i'


class _ImageMixin(object):
    activities = Column(
        Enum(name='activities', inherit_schema=True, *activities),
        nullable=False)

    height = Column(SmallInteger)


attributes = ['activities', 'height']


class Image(_ImageMixin, Document):
    """
    """
    __tablename__ = 'images'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        image = ArchiveImage()
        super(Image, self)._to_archive(image)
        copy_attributes(self, image, attributes)

        return image

    def update(self, other):
        super(Image, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveImage(_ImageMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'images_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }


schema_image = SQLAlchemySchemaNode(
    Image,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_document_locale]
        },
        'geometry': geometry_schema_overrides
    })

schema_update_image = get_update_schema(schema_image)
