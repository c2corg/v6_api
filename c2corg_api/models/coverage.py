from c2corg_api.models import schema
from c2corg_api.models.enums import coverage_types
from c2corg_api.models.document import (
    schema_document_locale,
    Document,
    get_geometry_schema_overrides,
    schema_attributes)
from c2corg_api.models.schema_utils import get_update_schema, \
    get_create_schema, restrict_schema
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.common.fields_coverage import fields_coverage
from colanderalchemy import SQLAlchemySchemaNode
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


schema_coverage_locale = schema_document_locale
schema_coverage_attributes = list(schema_attributes)

schema_coverage = SQLAlchemySchemaNode(
    Coverage,
    # whitelisted attributes
    includes=schema_coverage_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_coverage_locale]
        },
        'geometry': get_geometry_schema_overrides(['POLYGON'])
    })

schema_create_coverage = get_create_schema(schema_coverage)
schema_update_coverage = get_update_schema(schema_coverage)
schema_listing_coverage = restrict_schema(
    schema_coverage, fields_coverage.get('listing'))
