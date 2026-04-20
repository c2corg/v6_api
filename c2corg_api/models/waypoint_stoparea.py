from sqlalchemy import Column, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from c2corg_api.models import Base, schema
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.waypoint import Waypoint  # noqa: F401


class _WaypointStopareaMixin:
    distance: Mapped[float] = mapped_column(Float, nullable=False)

    @declared_attr
    def waypoint_stoparea_id(cls):  # noqa: N805
        return Column(Integer, primary_key=True)

    @declared_attr
    def stoparea_id(cls):  # noqa: N805
        return Column(
            Integer, ForeignKey(schema + '.stopareas.stoparea_id'), nullable=False
        )

    @declared_attr
    def waypoint_id(cls):  # noqa: N805
        return Column(
            Integer, ForeignKey(schema + '.waypoints.document_id'), nullable=False
        )


attributes = ['distance', 'stoparea_id', 'waypoint_id']


class WaypointStoparea(Base, _WaypointStopareaMixin):
    __tablename__ = 'waypoints_stopareas'
    __table_args__ = {'schema': schema, 'extend_existing': True}

    waypoint_stoparea_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    stoparea_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            schema + '.stopareas.stoparea_id',
            use_alter=True,
            name='fk_waypoint_stoparea_stoparea_id',
        ),
        nullable=False,
    )

    waypoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            schema + '.waypoints.document_id',
            use_alter=True,
            name='fk_waypoint_stoparea_waypoint_id',
        ),
        nullable=False,
    )

    distance: Mapped[float] = mapped_column(Float, nullable=False)

    waypoint = relationship('Waypoint', foreign_keys=[waypoint_id])

    def update(self, other):
        copy_attributes(other, self, attributes)
