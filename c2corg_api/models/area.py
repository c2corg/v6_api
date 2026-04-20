from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_area import fields_area
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    geometry_attributes,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.enums import area_type
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import copy_attributes

AREA_TYPE = document_types.AREA_TYPE


class _AreaMixin:
    area_type: Mapped[Optional[Any]] = mapped_column(area_type)


attributes = ['area_type']


class Area(_AreaMixin, Document):
    """ """

    __tablename__ = 'areas'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': Document.document_id == document_id,
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
    """ """

    __tablename__ = 'areas_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_area = build_field_spec(
    Area,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes,
    geometry_fields=geometry_attributes,
)

schema_listing_area = schema_area.restrict(fields_area.get('listing'))
