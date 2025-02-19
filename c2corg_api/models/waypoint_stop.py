from sqlalchemy import Column, Integer, Float, ForeignKey
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy.ext.declarative import declared_attr

from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema
from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, schema_attributes, get_geometry_schema_overrides
)
from c2corg_api.models.common import document_types
from sqlalchemy.orm import relationship
from c2corg_api.models.waypoint import Waypoint # don't remove this import



WAYPOINT_STOP_TYPE = document_types.WAYPOINT_STOP_TYPE

class _WaypointStopMixin:
    # Distance entre le waypoint et l'arrêt
    distance = Column(Float, nullable=False)

    @declared_attr
    def document_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.documents.document_id'),
            primary_key=True
        )
    
    @declared_attr
    def stop_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.stops.document_id'),
            nullable=False
        )
    
    @declared_attr
    def waypoint_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.waypoints.document_id'),
            nullable=False
        )

attributes = ['distance', 'stop_id', 'waypoint_id']

class WaypointStop(_WaypointStopMixin, Document):
   
    __tablename__ = 'waypoints_stops'
    __table_args__ = {
        'schema': schema,
        'extend_existing': True
    }

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        primary_key=True
    )

    stop_id = Column(
        Integer,
        ForeignKey(schema + '.stops.document_id', 
                  use_alter=True, 
                  name='fk_waypoint_stop_stop_id'),
        nullable=False
    )

    waypoint_id = Column(
        Integer,
        ForeignKey(schema + '.waypoints.document_id', 
                  use_alter=True, 
                  name='fk_waypoint_stop_waypoint_id'),
        nullable=False
    )

    distance = Column(Float, nullable=False)

    waypoint = relationship("Waypoint", foreign_keys=[waypoint_id])

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_STOP_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def update(self, other):
        super(WaypointStop, self).update(other)
        copy_attributes(other, self, attributes)

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
