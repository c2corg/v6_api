"""Schemas of the images."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.common.attributes import image_types
from c2corg_api.models.common.fields_image import fields_image
from c2corg_api.models.image import Image
from c2corg_api.schemas.base import ModelSchema, Schema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    LocaleSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import (
    DateTime,
    FiniteFloat,
    Int,
    Map,
    OneOf,
    Seq,
    Str,
)

ImageGeometrySchema = geometry_schema(['POINT'])


class ImageLocaleSchema(LocaleSchema):
    # an image may have no title
    title: Str(150) = ''


class ImageSchema(DocumentSchema):
    locales: Seq(ImageLocaleSchema) = []
    geometry: Map(ImageGeometrySchema) = None
    activities: Seq(OneOf(a.activities)) = None
    categories: Seq(OneOf(a.image_categories)) = None
    image_type: OneOf(image_types) = None
    author: Str(100) = None
    elevation: Int = None
    height: Int = None
    width: Int = None
    file_size: Int = None
    filename: Str(30)
    camera_name: Str(100) = None
    exposure_time: FiniteFloat = None
    focal_length: FiniteFloat = None
    fnumber: FiniteFloat = None
    iso_speed: Int = None
    date_time: DateTime = None


ImageCreateSchema = create_schema(ImageSchema, AssociationsSchema)
ImageUpdateSchema = update_schema(ImageCreateSchema)


class ImageListCreateSchema(Schema):
    images: Seq(ImageCreateSchema) = None


image_schema = ModelSchema(
    Image,
    ImageSchema,
    document_children(locale_schema=ImageLocaleSchema, geometry=ImageGeometrySchema),
)
image_listing_schema = image_schema.restrict(fields_image.get('listing'))
