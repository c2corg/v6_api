"""GeoJSON geometry fields, like `colander_ext.Geometry`."""

from functools import partial
from numbers import Number
from typing import Annotated

import geojson
from geoalchemy2 import WKBElement
from pydantic import BeforeValidator
from pydantic_core import PydanticCustomError

from c2corg_api.ext.wkb import wkbelement_from_geojson
from c2corg_api.schemas.types import Empty


def _invalid(value):
    return PydanticCustomError(
        'invalid_geometry', 'Invalid geometry: {value}', {'value': str(value)}
    )


def _position_error(position):
    # 2, 3 or 4 values: the 4th is the time of GPS tracks (M coordinate),
    # which plain geojson rejects
    if not isinstance(position, list):
        return 'each position must be a list'
    if len(position) not in (2, 3, 4):
        return 'a position must have exactly 2, 3 or 4 values'
    if not all(isinstance(number, Number) for number in position):
        return 'a position cannot have inner positions'
    return None


def _line_error(line):
    if not isinstance(line, list):
        return 'each line must be a list of positions'
    if len(line) < 2:
        return 'the "coordinates" member must be an array of two or more positions'
    return next(filter(None, map(_position_error, line)), None)


def _polygon_error(polygon):
    if not isinstance(polygon, list):
        return 'Each polygon must be a list of linear rings'
    for ring in polygon:
        if not isinstance(ring, list):
            return "Each element of a polygon's coordinates must be a list"
        if len(ring) < 4:
            return 'Each linear ring must contain at least 4 positions'
        if ring[0] != ring[-1]:
            return 'Each linear ring must end where it started'
        error = next(filter(None, map(_position_error, ring)), None)
        if error:
            return error
    return None


def _each(check, items):
    if not isinstance(items, list):
        return 'coordinates must be a list'
    return next(filter(None, map(check, items)), None)


_CHECKS = {
    'POINT': _position_error,
    'MULTIPOINT': partial(_each, _position_error),
    'LINESTRING': _line_error,
    'MULTILINESTRING': partial(_each, _line_error),
    'POLYGON': _polygon_error,
    'MULTIPOLYGON': partial(_each, _polygon_error),
}


def _to_wkb(value, geometry_types, srid):
    """Convert a GeoJSON string into a `WKBElement`, checking its type."""
    if value is None or value == '':
        # an empty geometry, like a missing one
        return None
    if isinstance(value, WKBElement):
        return value
    try:
        data = geojson.loads(value)
        geom_type = data['type'].upper()
    except Exception as e:
        raise _invalid(value) from e
    if geom_type not in geometry_types:
        raise PydanticCustomError(
            'invalid_geometry_type',
            'Invalid geometry type. Expected: {expected}. Got: {got}.',
            {'expected': str(geometry_types), 'got': geom_type},
        )
    check = _CHECKS.get(geom_type)
    if check is None or check(data.get('coordinates')):
        raise _invalid(value)
    return wkbelement_from_geojson(data, srid)


def Geometry(geometry_types, srid=3857):  # noqa: N802 (used like a type)
    """Return a GeoJSON geometry type limited to the given geometry types."""
    types = [t.upper() for t in geometry_types]
    return Annotated[
        WKBElement | None,
        Empty(lambda value: value is None or value == ''),
        BeforeValidator(partial(_to_wkb, geometry_types=types, srid=srid)),
    ]
