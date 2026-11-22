from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, func

from c2corg_api.models import Base, schema
from c2corg_api.models.enums import coverage_types


class NavitiaCoverage(Base):
    """A region of Navitia, the public transport API.

    France is divided into a few coverages ('fr-idf', 'fr-ne', 'fr-nw',
    'fr-se', 'fr-sw'). The isochrones need the coverage of their source, and
    the journeys give better results with the coverage of their destination.

    Reference data, not a document: no history, no locale, no association.
    `scripts/navitia/update_coverages.py` loads them from Navitia, to run
    again when Navitia changes its coverages.

    See https://doc.navitia.io/#coverage
    """

    __tablename__ = 'navitia_coverages'
    __table_args__ = {'schema': schema}

    coverage_type = Column(coverage_types, primary_key=True)
    # in longitude and latitude, as Navitia gives them
    geom = Column(
        Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=False),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
