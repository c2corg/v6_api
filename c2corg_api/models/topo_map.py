from c2corg_api.models.enums import map_editor, map_scale
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String
    )

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document,
    schema_attributes, schema_locale_attributes, geometry_attributes)
from c2corg_api.models.common import document_types

MAP_TYPE = document_types.MAP_TYPE


class _MapMixin(object):
    editor = Column(map_editor)
    scale = Column(map_scale)
    code = Column(String)


attributes = [
    'editor', 'scale', 'code'
]


class TopoMap(_MapMixin, Document):
    """
    """
    __tablename__ = 'maps'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        m = ArchiveTopoMap()
        super(TopoMap, self)._to_archive(m)
        copy_attributes(self, m, attributes)

        return m

    def update(self, other):
        super(TopoMap, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveTopoMap(_MapMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'maps_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


schema_topo_map = build_field_spec(
    TopoMap,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_topo_map = schema_topo_map.restrict(
    fields_topo_map.get('listing'))


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

_topo_map_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_TopoMapDocBase = schema_from_sa_model(
    TopoMap,
    name='_TopoMapDocBase',
    includes=_topo_map_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
    },
)


class TopoMapDocumentSchema(
    _DuplicateLocalesMixin, _TopoMapDocBase,
):
    """Full topo map document for create/update requests."""
    locales: Optional[List[DocumentLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateTopoMapSchema = pydantic_create_schema(
    TopoMapDocumentSchema,
    name='CreateTopoMapSchema',
)

UpdateTopoMapSchema = pydantic_update_schema(
    TopoMapDocumentSchema,
    name='UpdateTopoMapSchema',
)
