from c2corg_api.models import schema, Base
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_geometry_schema_overrides,
    schema_document_locale, schema_attributes)
from c2corg_api.models.enums import area_type
from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.common.fields_area import fields_area
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from c2corg_api.models.common import document_types

AREA_TYPE = document_types.AREA_TYPE


class _AreaMixin(object):
    area_type = Column(area_type)


attributes = ['area_type']


class Area(_AreaMixin, Document):
    """
    """
    __tablename__ = 'areas'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        area = ArchiveArea()
        super(Area, self)._to_archive(area)
        copy_attributes(self, area, attributes)

        return area

    def update(self, other):
        super(Area, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveArea(_AreaMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'areas_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


schema_area = SQLAlchemySchemaNode(
    Area,
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
        'geometry': get_geometry_schema_overrides(['POLYGON', 'MULTIPOLYGON'])
    })

schema_create_area = get_create_schema(schema_area)
schema_update_area = get_update_schema(schema_area)
schema_listing_area = restrict_schema(
    schema_area, fields_area.get('listing'))


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

_area_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_AreaDocBase = schema_from_sa_model(
    Area,
    name='_AreaDocBase',
    includes=_area_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
    },
)


class AreaDocumentSchema(
    _DuplicateLocalesMixin, _AreaDocBase,
):
    """Full area document for create/update requests."""
    locales: Optional[List[DocumentLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateAreaSchema = pydantic_create_schema(
    AreaDocumentSchema,
    name='CreateAreaSchema',
)

UpdateAreaSchema = pydantic_update_schema(
    AreaDocumentSchema,
    name='UpdateAreaSchema',
)
