from sqlalchemy import Column, Integer, Float, ForeignKey
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy.ext.declarative import declared_attr

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import get_geometry_schema_overrides
from sqlalchemy.orm import relationship
from c2corg_api.models.waypoint import Waypoint  # don't remove this import  # noqa: F401, E501


class _WaypointStopareaMixin:
    distance = Column(Float, nullable=False)

    @declared_attr
    def waypoint_stoparea_id(cls):
        return Column(
            Integer,
            primary_key=True
        )

    @declared_attr
    def stoparea_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.stopareas.stoparea_id'),
            nullable=False
        )

    @declared_attr
    def waypoint_id(cls):
        return Column(
            Integer,
            ForeignKey(schema + '.waypoints.document_id'),
            nullable=False
        )


attributes = ['distance', 'stoparea_id', 'waypoint_id']


class WaypointStoparea(Base, _WaypointStopareaMixin):

    __tablename__ = 'waypoints_stopareas'
    __table_args__ = {
        'schema': schema,
        'extend_existing': True
    }

    waypoint_stoparea_id = Column(
        Integer,
        primary_key=True
    )

    stoparea_id = Column(
        Integer,
        ForeignKey(schema + '.stopareas.stoparea_id',
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

    def update(self, other):
        copy_attributes(other, self, attributes)


schema_waypoint_stoparea = SQLAlchemySchemaNode(
    WaypointStoparea,
    includes=attributes,
    overrides={
        'waypoint_stoparea_id': {'missing': None},
        'geometry': get_geometry_schema_overrides(['POINT'])
    }
)
