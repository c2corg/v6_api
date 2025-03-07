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



WAYPOINT_STOPAREA_TYPE = document_types.WAYPOINT_STOPAREA_TYPE

class _WaypointStopareaMixin:
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
    def stoparea_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.stopareas.document_id'),
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

class WaypointStoparea(_WaypointStopareaMixin, Document):
   
    __tablename__ = 'waypoints_stopareas'
    __table_args__ = {
        'schema': schema,
        'extend_existing': True
    }

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        primary_key=True
    )

    stoparea_id = Column(
        Integer,
        ForeignKey(schema + '.stopareas.document_id', 
                  use_alter=True, 
                  name='fk_waypoint_stoparea_stoparea_id'),
        nullable=False
    )

    waypoint_id = Column(
        Integer,
        ForeignKey(schema + '.waypoints.document_id', 
                  use_alter=True, 
                  name='fk_waypoint_stoparea_waypoint_id'),
        nullable=False
    )

    distance = Column(Float, nullable=False)

    waypoint = relationship("Waypoint", foreign_keys=[waypoint_id])

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_STOPAREA_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def update(self, other):
        super(WaypointStoparea, self).update(other)
        copy_attributes(other, self, attributes)

schema_waypoint_stoparea = SQLAlchemySchemaNode(
    WaypointStoparea,
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {'missing': None},
        'version': {'missing': None},
        'geometry': get_geometry_schema_overrides(['POINT'])
    }
)

schema_update_waypoint_stoparea = get_create_schema(schema_waypoint_stoparea)
schema_create_waypoint_stoparea = get_update_schema(schema_waypoint_stoparea)
