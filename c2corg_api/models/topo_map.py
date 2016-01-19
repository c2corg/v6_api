from c2corg_api.models.enums import map_editor, map_scale
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_update_schema, geometry_schema_overrides,
    schema_document_locale, schema_attributes)

MAP_TYPE = 'm'


class _MapMixin(object):
    editor = Column(map_editor)
    scale = Column(map_scale)
    code = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE
    }

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
        'geometry': geometry_schema_overrides
    })

schema_update_topo_map = get_update_schema(schema_topo_map)
