from c2corg_api.models.schema_utils import restrict_schema,\
    get_update_schema, get_create_schema
from c2corg_common.fields_image import fields_image
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, enums, Base
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_api.models.document import (
    ArchiveDocument, Document, geometry_schema_overrides,
    schema_document_locale, schema_attributes)
from c2corg_common import document_types

IMAGE_TYPE = document_types.IMAGE_TYPE


class _ImageMixin(object):

    activities = Column(ArrayOfEnum(enums.activity_type))

    categories = Column(ArrayOfEnum(enums.image_category))

    image_type = Column(enums.image_type)

    author = Column(String(100))

    has_svg = Column(Boolean)

    elevation = Column(SmallInteger)

    height = Column(SmallInteger)

    width = Column(SmallInteger)

    file_size = Column(Integer)

    filename = Column(String(30))

    date_time = Column(DateTime)

    camera_name = Column(String(100))

    exposure_time = Column(Float)

    focal_length = Column(Float)

    fnumber = Column(Float)

    iso_speed = Column(SmallInteger)


attributes = [
    'activities', 'categories', 'image_type', 'author', 'has_svg', 'elevation',
    'height', 'width', 'file_size', 'filename', 'camera_name', 'exposure_time',
    'focal_length', 'fnumber', 'iso_speed', 'date_time'
]


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

    __table_args__ = Base.__table_args__


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

schema_create_image = get_create_schema(schema_image)
schema_update_image = get_update_schema(schema_image)
schema_listing_image = restrict_schema(
    schema_image, fields_image.get('listing'))
schema_association_image = restrict_schema(schema_image, [
    'filename', 'locales.title'
])
