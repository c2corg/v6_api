from c2corg_api.models import schema
from c2corg_api.models.enums import coverage_types
from c2corg_api.models.document import (
    Document,
    schema_attributes, schema_locale_attributes, geometry_attributes)
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.common.fields_coverage import fields_coverage
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
)
from c2corg_api.models.common import document_types

COVERAGE_TYPE = document_types.COVERAGE_TYPE


class _CoverageMixin(object):
    coverage_type = Column(coverage_types)


attributes = ['coverage_type']


class Coverage(_CoverageMixin, Document):
    """
    Represents a Navitia Coverage, which defines a specific geographical area.

    For example, France is divided into multiple coverages:
    - 'fr-se' : South-East France
    - 'fr-ne' : North-East France
    - 'fr-nw' : North-West France
    - 'fr-sw' : South-West France
    - 'fr-idf': Île-de-France region

    They are defined by Navitia, and might get updated,
    hence the script 'update_navitia_coverage'

    Usage:
        Coverage is used to get more results when using journey API,
        and is required when using Isochrone API

    More information:
        See the Navitia documentation for coverage details:
        https://doc.navitia.io/#coverage
    """
    __tablename__ = 'coverages'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': COVERAGE_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def update(self, other):
        super(Coverage, self).update(other)
        copy_attributes(other, self, attributes)


schema_coverage_attributes = list(schema_attributes)

schema_coverage = build_field_spec(
    Coverage,
    includes=schema_coverage_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_coverage = schema_coverage.restrict(
    fields_coverage.get('listing'))


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

_coverage_schema_attrs = [
    a for a in schema_coverage_attributes + attributes
    if a not in ('locales', 'geometry')
]

_CoverageDocBase = schema_from_sa_model(
    Coverage,
    name='_CoverageDocBase',
    includes=_coverage_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
    },
)


class CoverageDocumentSchema(
    _DuplicateLocalesMixin, _CoverageDocBase,
):
    """Full coverage document for create/update requests."""
    locales: Optional[List[DocumentLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateCoverageSchema = pydantic_create_schema(
    CoverageDocumentSchema,
    name='CreateCoverageSchema',
)

UpdateCoverageSchema = pydantic_update_schema(
    CoverageDocumentSchema,
    name='UpdateCoverageSchema',
)
