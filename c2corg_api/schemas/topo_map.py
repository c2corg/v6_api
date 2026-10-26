"""Schemas of the maps."""

from c2corg_api.models.common.attributes import map_editors, map_scales
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Map, OneOf, Str

TopoMapGeometrySchema = geometry_schema(['POLYGON', 'MULTIPOLYGON'])


class TopoMapSchema(DocumentSchema):
    geometry: Map(TopoMapGeometrySchema) = None
    editor: OneOf(map_editors) = None
    scale: OneOf(map_scales) = None
    code: Str() = None


# a map is created without associations (they follow from its geometry)
TopoMapCreateSchema = TopoMapSchema
TopoMapUpdateSchema = update_schema(create_schema(TopoMapSchema, AssociationsSchema))

topo_map_schema = ModelSchema(
    TopoMap, TopoMapSchema, document_children(geometry=TopoMapGeometrySchema)
)
topo_map_listing_schema = topo_map_schema.restrict(fields_topo_map.get('listing'))
