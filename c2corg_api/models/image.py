from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.common.fields_image import fields_image
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String
    )
from sqlalchemy.orm import declared_attr

from c2corg_api.models import schema, enums, Base, DBSession
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_api.models.document import (
    ArchiveDocument, Document,
    schema_attributes, schema_locale_attributes, geometry_attributes)
from c2corg_api.models.common import document_types

IMAGE_TYPE = document_types.IMAGE_TYPE


class _ImageMixin(object):

    activities = Column(ArrayOfEnum(enums.activity_type))

    categories = Column(ArrayOfEnum(enums.image_category))

    image_type = Column(enums.image_type)

    author = Column(String(100))

    elevation = Column(SmallInteger)

    height = Column(SmallInteger)

    width = Column(SmallInteger)

    file_size = Column(Integer)

    @declared_attr
    def filename(self):
        return Column(String(30),
                      nullable=False,
                      unique=(self.__name__ == 'Image'))

    date_time = Column(DateTime(timezone=True))

    camera_name = Column(String(100))

    exposure_time = Column(Float)

    focal_length = Column(Float)

    fnumber = Column(Float)

    iso_speed = Column(SmallInteger)


attributes = [
    'activities', 'categories', 'image_type', 'author', 'elevation',
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


schema_image = build_field_spec(
    Image,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_image = schema_image.restrict(
    fields_image.get('listing'))


def is_personal(image_id):
    image_type = DBSession.query(Image.image_type). \
        select_from(Image.__table__). \
        filter(Image.document_id == image_id). \
        scalar()
    return image_type == 'personal'


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    get_create_schema as pydantic_create_schema,
    DocumentLocaleSchema,
    DocumentGeometrySchema,
    AssociationsSchema,
    _DuplicateLocalesMixin,
)
from typing import List, Optional  # noqa: E402
from pydantic import BaseModel as _BaseModel, field_validator  # noqa: E402

_image_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_ImageDocBase = schema_from_sa_model(
    Image,
    name='_ImageDocBase',
    includes=_image_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
        'filename': {'default': ...},
    },
)


class ImageLocaleSchema(DocumentLocaleSchema):
    """Image locales: images can be created without a title."""
    title: Optional[str] = ''

    @field_validator('title', mode='before')
    @classmethod
    def _coerce_none_title(cls, v):
        """The schema used ``missing=''`` so that ``None`` / absent title
        became the empty string.  Reproduce that here."""
        if v is None:
            return ''
        return v


class ImageDocumentSchema(
    _DuplicateLocalesMixin, _ImageDocBase,
):
    """Full image document for create/update requests."""
    locales: Optional[List[ImageLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateImageSchema = pydantic_create_schema(
    ImageDocumentSchema,
    name='CreateImageSchema',
)

UpdateImageSchema = pydantic_update_schema(
    ImageDocumentSchema,
    name='UpdateImageSchema',
)


class CreateImageListSchema(_BaseModel):
    images: Optional[List[ImageDocumentSchema]] = None
