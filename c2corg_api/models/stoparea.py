from sqlalchemy import Column, Integer, String
from geoalchemy2.types import Geometry
from colanderalchemy import SQLAlchemySchemaNode
import colander
from geoalchemy2 import shape


from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes


class _StopareaMixin:
    navitia_id = Column(String, nullable=False)
    stoparea_name = Column(String, nullable=False)
    line = Column(String, nullable=False)
    operator = Column(String, nullable=False)
    # same SRID as the stopareas table created by the migration and as the
    # points written by the Navitia import (EPSG:3857, like the waypoints)
    geom = Column(Geometry('POINT', srid=3857, management=True))


attributes = ['navitia_id', 'stoparea_name', 'line', 'operator', 'geom']


class Stoparea(Base, _StopareaMixin):
    """
    Stoparea model representing a stop area
    """
    __tablename__ = 'stopareas'
    __table_args__ = {
        'schema': schema,
        'extend_existing': True
    }

    stoparea_id = Column(Integer, primary_key=True)

    def update(self, other):
        copy_attributes(other, self, attributes)

    def to_dict(self):
        return {
            "id": self.stoparea_id,
            "navitia_id": self.navitia_id,
            "stoparea_name": self.stoparea_name,
            "line": self.line,
            "operator": self.operator,
            "coordinates": {
                "x": shape.to_shape(self.geom).x,
                "y": shape.to_shape(self.geom).y
            } if self.geom is not None else None
        }


schema_stoparea = SQLAlchemySchemaNode(
    Stoparea,
    includes=attributes,
    overrides={
        'stoparea_id': {'missing': None},
        'geom': {'typ': colander.String()}
    }
)
