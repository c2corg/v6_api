"""
Coverage helpers.

Extracted from ``c2corg_api.views.coverage``.
"""

from shapely.geometry import Point

from c2corg_api.models.coverage import Coverage
from c2corg_api.models.utils import wkb_to_shape


def get_coverage(lon, lat, db):
    """Get the coverage that contains a point(lon, lat)."""
    pt = Point(lon, lat)

    coverages = db.query(Coverage).all()

    for coverage in coverages:
        geom = coverage.geometry.geom_detail
        poly = wkb_to_shape(geom)
        if poly.contains(pt):
            return coverage.coverage_type

    return None
