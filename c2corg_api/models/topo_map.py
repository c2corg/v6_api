from c2corg_api.models.enums import map_editor, map_scale
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.views import set_best_locale
from c2corg_common.fields_topo_map import fields_topo_map
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, DBSession
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_update_schema, geometry_schema_overrides,
    schema_document_locale, schema_attributes, DocumentGeometry,
    DocumentLocale)
from sqlalchemy.orm import load_only, joinedload

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
schema_listing_topo_map = restrict_schema(
    schema_topo_map, fields_topo_map.get('listing'))


# TODO cache on document_id and lang (empty the cache if the document geometry
# has changed or any maps was updated/created)
def get_maps(document, lang):
    """Load and return maps that intersect with the document geometry.
    """
    if document.geometry is None:
        return []

    topo_maps = DBSession. \
        query(TopoMap). \
        join(
            DocumentGeometry,
            TopoMap.document_id == DocumentGeometry.document_id). \
        options(load_only(
            TopoMap.document_id, TopoMap.editor, TopoMap.code,
            TopoMap.version)). \
        options(joinedload(TopoMap.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title,
            DocumentLocale.version)). \
        filter(
            DocumentGeometry.geom.intersects(
                DBSession.query(DocumentGeometry.geom).filter(
                    DocumentGeometry.document_id == document.document_id)
            )). \
        all()

    if lang is not None:
        set_best_locale(topo_maps, lang)

    return topo_maps
