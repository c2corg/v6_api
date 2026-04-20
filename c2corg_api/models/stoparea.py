from typing import Optional

from geoalchemy2 import shape
from geoalchemy2.types import Geometry
from sqlalchemy import Any, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, schema
from c2corg_api.models.utils import copy_attributes


class _StopareaMixin:
    navitia_id: Mapped[str] = mapped_column(String, nullable=False)
    stoparea_name: Mapped[str] = mapped_column(String, nullable=False)
    line: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    geom: Mapped[Optional[Any]] = mapped_column(Geometry('POINT', srid=3857))


attributes = ['navitia_id', 'stoparea_name', 'line', 'operator', 'geom']


class Stoparea(Base, _StopareaMixin):
    """
    Stoparea model representing a stop area
    """

    __tablename__ = 'stopareas'
    __table_args__ = {'schema': schema, 'extend_existing': True}

    stoparea_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    def update(self, other):
        copy_attributes(other, self, attributes)

    def to_dict(self):
        return {
            'id': self.stoparea_id,
            'navitia_id': self.navitia_id,
            'stoparea_name': self.stoparea_name,
            'line': self.line,
            'operator': self.operator,
            'coordinates': {
                'x': shape.to_shape(self.geom).x,
                'y': shape.to_shape(self.geom).y,
            }
            if self.geom is not None
            else None,
        }
