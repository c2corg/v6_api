from sqlalchemy import Column, ForeignKey, Integer

from c2corg_api.models import Base, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
)
from c2corg_api.models.enums import area_type
from c2corg_api.models.utils import copy_attributes

AREA_TYPE = document_types.AREA_TYPE


class _AreaMixin:
    area_type = Column(area_type)


attributes = ['area_type']


class Area(_AreaMixin, Document):
    """Current version of an area."""

    __tablename__ = 'areas'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        area = ArchiveArea()
        super()._to_archive(area)
        copy_attributes(self, area, attributes)

        return area

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveArea(_AreaMixin, ArchiveDocument):
    """Archived version of an area."""

    __tablename__ = 'areas_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': AREA_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__
