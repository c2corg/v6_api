from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    SmallInteger,
    Boolean
    )
from colanderalchemy import SQLAlchemySchemaNode

from . import Base


class Summit(Base):
    __tablename__ = 'app_summits_archives'

    id = Column(Integer, primary_key=True)
    lon = Column(Numeric(9, 6))
    lat = Column(Numeric(9, 6))
    elevation = Column(SmallInteger)
    is_latest_version = Column(Boolean)

# Index('my_index', MyModel.name, unique=True, mysql_length=255)

schema_summit = SQLAlchemySchemaNode(
    Summit,
    # whitelisted attributes
    includes=['id', 'lon', 'lat', 'elevation'])
