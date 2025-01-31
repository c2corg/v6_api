from sqlalchemy import Column, Integer, Float, ForeignKey
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy.orm import relationship


from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, schema_attributes, get_geometry_schema_overrides
)
from c2corg_api.models.common import document_types

WAYPOINT_STOP_TYPE = document_types.WAYPOINT_STOP_TYPE

class _WaypointStopMixin(object):
    # Distance entre le waypoint et l'arrêt
    distance = Column(Float, nullable=False)


attributes = ['distance']


class WaypointStop(_WaypointStopMixin, Document, Base):
    """
    Modélise la relation entre un Waypoint et un Stop.
    """
    __tablename__ = 'waypoints_stops'
    __table_args__ = {'extend_existing': True}

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        primary_key=True
    )

    waypoint_id = Column(
        Integer,
        ForeignKey(schema + '.waypoints.document_id'),
        nullable=False
    )

    stop_id = Column(
        Integer,
        ForeignKey(schema + '.stops.document_id'),
        nullable=False
    )

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_STOP_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    id = Column(Integer, primary_key=True)
    waypoint = relationship("Waypoint", back_populates="waypoints_stops")

    def to_archive(self):
        waypoint_stop = ArchiveWaypointStop()
        super(WaypointStop, self)._to_archive(waypoint_stop)
        copy_attributes(self, waypoint_stop, attributes)
        return waypoint_stop

    def update(self, other):
        super(WaypointStop, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveWaypointStop(_WaypointStopMixin, ArchiveDocument):
    """
    Archive de WaypointStop.
    """
    __tablename__ = 'waypoints_stops_archives'
    __table_args__ = {'extend_existing': True}

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'),
        primary_key=True
    )
    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_STOP_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


schema_waypoint_stop = SQLAlchemySchemaNode(
    WaypointStop,
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {'missing': None},
        'version': {'missing': None},
        'geometry': get_geometry_schema_overrides(['POINT'])
    }
)

schema_update_waypoint_stop = get_create_schema(schema_waypoint_stop)
schema_create_waypoint_stop = get_update_schema(schema_waypoint_stop)