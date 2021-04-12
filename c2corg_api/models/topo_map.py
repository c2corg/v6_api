from c2corg_api.models.enums import map_editor, map_scale
from c2corg_api.models.schema_utils import restrict_schema, get_update_schema
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_geometry_schema_overrides,
    schema_document_locale, schema_attributes)
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


schema_topo_map = SQLAlchemySchemaNode(
    TopoMap,
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

schema_update_topo_map = get_update_schema(schema_topo_map)
schema_listing_topo_map = restrict_schema(
    schema_topo_map, fields_topo_map.get('listing'))
