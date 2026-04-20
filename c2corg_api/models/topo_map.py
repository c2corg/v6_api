from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    geometry_attributes,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.enums import map_editor, map_scale
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import copy_attributes

MAP_TYPE = document_types.MAP_TYPE


class _MapMixin:
    editor: Mapped[Optional[Any]] = mapped_column(map_editor)
    scale: Mapped[Optional[Any]] = mapped_column(map_scale)
    code: Mapped[Optional[str]] = mapped_column(String)


attributes = ['editor', 'scale', 'code']


class TopoMap(_MapMixin, Document):
    """ """

    __tablename__ = 'maps'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': Document.document_id == document_id,
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
    """ """

    __tablename__ = 'maps_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': MAP_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_topo_map = build_field_spec(
    TopoMap,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_topo_map = schema_topo_map.restrict(fields_topo_map.get('listing'))
