from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from c2corg_api.models import Base, DBSession, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_image import fields_image
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    geometry_attributes,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

IMAGE_TYPE = document_types.IMAGE_TYPE


class _ImageMixin:
    activities: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.activity_type)
    )

    categories: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.image_category)
    )

    image_type: Mapped[Optional[str]] = mapped_column(enums.image_type)

    author: Mapped[Optional[str]] = mapped_column(String(100))

    elevation: Mapped[Optional[int]] = mapped_column(SmallInteger)

    height: Mapped[Optional[int]] = mapped_column(SmallInteger)

    width: Mapped[Optional[int]] = mapped_column(SmallInteger)

    file_size: Mapped[Optional[int]] = mapped_column(Integer)

    @declared_attr
    def filename(self):
        return Column(String(30), nullable=False, unique=(self.__name__ == 'Image'))

    date_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    camera_name: Mapped[Optional[str]] = mapped_column(String(100))

    exposure_time: Mapped[Optional[float]] = mapped_column(Float)

    focal_length: Mapped[Optional[float]] = mapped_column(Float)

    fnumber: Mapped[Optional[float]] = mapped_column(Float)

    iso_speed: Mapped[Optional[int]] = mapped_column(SmallInteger)


attributes = [
    'activities',
    'categories',
    'image_type',
    'author',
    'elevation',
    'height',
    'width',
    'file_size',
    'filename',
    'camera_name',
    'exposure_time',
    'focal_length',
    'fnumber',
    'iso_speed',
    'date_time',
]


class Image(_ImageMixin, Document):
    """ """

    __tablename__ = 'images'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': Document.document_id == document_id,
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
    """ """

    __tablename__ = 'images_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_image = build_field_spec(
    Image,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_image = schema_image.restrict(fields_image.get('listing'))


def is_personal(image_id):
    image_type = (
        DBSession.query(Image.image_type)
        .select_from(Image.__table__)
        .filter(Image.document_id == image_id)
        .scalar()
    )
    return image_type == 'personal'
