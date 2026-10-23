from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import Column, ForeignKey, Integer, String

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    get_geometry_schema_overrides,
    schema_attributes,
    schema_document_locale,
)
from c2corg_api.models.enums import map_editor, map_scale
from c2corg_api.models.schema_utils import get_update_schema, restrict_schema
from c2corg_api.models.utils import copy_attributes

MAP_TYPE = document_types.MAP_TYPE


class _MapMixin:
    editor = Column(map_editor)
    scale = Column(map_scale)
    code = Column(String)


attributes = ['editor', 'scale', 'code']


class TopoMap(_MapMixin, Document):
    """Current version of a map."""

    __tablename__ = 'maps'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        m = ArchiveTopoMap()
        super()._to_archive(m)
        copy_attributes(self, m, attributes)

        return m

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveTopoMap(_MapMixin, ArchiveDocument):
    """Archived version of a map."""

    __tablename__ = 'maps_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_topo_map = SQLAlchemySchemaNode(
    TopoMap,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {'missing': None},
        'version': {'missing': None},
        'locales': {'children': [schema_document_locale]},
        'geometry': get_geometry_schema_overrides(['POLYGON', 'MULTIPOLYGON']),
    },
)

schema_update_topo_map = get_update_schema(schema_topo_map)
schema_listing_topo_map = restrict_schema(
    schema_topo_map, fields_topo_map.get('listing')
)
