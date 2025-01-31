from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey
)

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    schema_attributes, schema_locale_attributes,
    get_geometry_schema_overrides
)

STOP_TYPE = "stop"


class _StopMixin(object):
    stop_name = Column(String, nullable=False)
    line = Column(String, nullable=False)
    operator = Column(String, nullable=False)


attributes = ['stop_name', 'line', 'operator']


class Stop(_StopMixin, Document, Base):
    """
    """
    __tablename__ = 'stops'
    __table_args__ = {'extend_existing': True}

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': STOP_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        stop = ArchiveStop()
        super(Stop, self)._to_archive(stop)
        copy_attributes(self, stop, attributes)
        return stop

    def update(self, other):
        super(Stop, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveStop(_StopMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'stops_archives'
    __table_args__ = {'extend_existing': True}

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': STOP_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


class WaypointStop(Base):
    """
    Association entre un Waypoint et un Stop
    """
    __tablename__ = 'waypoints_stops'

    waypoint_id = Column(Integer, ForeignKey(schema + '.waypoints.document_id'), primary_key=True)
    stop_id = Column(Integer, ForeignKey(schema + '.stops.document_id'), primary_key=True)


schema_stop = SQLAlchemySchemaNode(
    Stop,
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {'missing': None},
        'version': {'missing': None},
        'geometry': get_geometry_schema_overrides(['POINT'])
    }
)

schema_create_stop = get_create_schema(schema_stop)
schema_update_stop = get_update_schema(schema_stop)
