"""Schemas of the areas."""

from c2corg_api.models.area import Area
from c2corg_api.models.common.attributes import area_types
from c2corg_api.models.common.fields_area import fields_area
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Map, OneOf

AreaGeometrySchema = geometry_schema(['POLYGON', 'MULTIPOLYGON'])


class AreaSchema(DocumentSchema):
    geometry: Map(AreaGeometrySchema) = None
    area_type: OneOf(area_types) = None


AreaCreateSchema = create_schema(AreaSchema, AssociationsSchema)
AreaUpdateSchema = update_schema(AreaCreateSchema)

area_schema = ModelSchema(
    Area, AreaSchema, document_children(geometry=AreaGeometrySchema)
)
area_listing_schema = area_schema.restrict(fields_area.get('listing'))
