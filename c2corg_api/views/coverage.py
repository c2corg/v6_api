"""The coverages of Navitia (public transport API): which one a place is in."""

import json
import logging
import math

from shapely.errors import ShapelyError
from shapely.geometry import shape
from sqlalchemy import func

from c2corg_api.models import DBSession
from c2corg_api.models.coverage import NavitiaCoverage
from c2corg_api.views.resource import write

log = logging.getLogger(__name__)

# the coverages are in longitude and latitude
SRID = 4326


def validate_lon_lat(request, **kwargs):
    """Check that the required lon and lat are finite numbers."""
    for key in ('lon', 'lat'):
        try:
            value = float(request.GET[key])
            if not math.isfinite(value):
                raise ValueError
            request.validated[key] = value
        except KeyError, ValueError:
            request.errors.add('querystring', key, 'invalid ' + key)


def find_coverage(request):
    """Return the coverage from a longitude and a latitude."""
    lon = request.validated['lon']
    lat = request.validated['lat']

    return get_coverage(lon, lat)


def validate_geom_detail(request, **kwargs):
    """Check that geom_detail is a GeoJSON geometry, given as a string."""
    # an invalid JSON body raises here: the catch-all error view answers it
    body = request.json_body
    try:
        request.validated['polygon'] = shape(json.loads(body['geom_detail']))
    except KeyError, TypeError, ValueError, AttributeError, ShapelyError:
        request.errors.add('body', 'geom_detail', 'invalid geom_detail')


@write(validators=[validate_geom_detail], json=False)
def coverage_of_a_polygon(request):
    """Return the coverages for a geom_detail polygon.

    Returns the coverages from a geom_detail type polygon
    (geom_detail has to be EPSG 4326 since isochrone is 4326).
    """
    return get_coverages(request.validated['polygon'])


def get_coverage(lon, lat):
    """Return the type of the coverage containing a point, or None."""
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID)
    return (
        DBSession.query(NavitiaCoverage.coverage_type)
        .filter(func.ST_Contains(NavitiaCoverage.geom, point))
        .order_by(NavitiaCoverage.coverage_type)
        .limit(1)
        .scalar()
    )


def get_coverages(polygon):
    """Return the types of the coverages a geometry intersects."""
    geom = func.ST_GeomFromText(polygon.wkt, SRID)
    return [
        coverage_type
        for (coverage_type,) in DBSession.query(NavitiaCoverage.coverage_type)
        .filter(func.ST_Intersects(NavitiaCoverage.geom, geom))
        .order_by(NavitiaCoverage.coverage_type)
    ]
