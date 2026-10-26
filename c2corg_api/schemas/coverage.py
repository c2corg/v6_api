"""Schemas of the coverages (Navitia regions)."""

from c2corg_api.models.common.attributes import coverage_types
from c2corg_api.models.common.fields_coverage import fields_coverage
from c2corg_api.models.coverage import Coverage
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Map, OneOf

CoverageGeometrySchema = geometry_schema(['POLYGON'])


class CoverageSchema(DocumentSchema):
    geometry: Map(CoverageGeometrySchema) = None
    coverage_type: OneOf(coverage_types) = None


CoverageCreateSchema = create_schema(CoverageSchema, AssociationsSchema)
CoverageUpdateSchema = update_schema(CoverageCreateSchema)

coverage_schema = ModelSchema(
    Coverage, CoverageSchema, document_children(geometry=CoverageGeometrySchema)
)
coverage_listing_schema = coverage_schema.restrict(fields_coverage.get('listing'))
