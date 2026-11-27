"""Conversions between GeoJSON and the WKB of the geometry columns."""

import math
import struct

import geojson
from geoalchemy2 import WKBElement
from geomet import wkb

# EWKB SRID flag, see https://git.osgeo.org/gitea/postgis/postgis/raw/
# master/doc/ZMSgeoms.txt
_EWKB_SRID_FLAG = 0x20000000


def wkbelement_from_geojson(geojson, srid):
    geometry = wkb.dumps(geojson, big_endian=False)
    if srid and srid > 0:
        # Embed the SRID directly in the WKB header, turning it into EWKB.
        # geoalchemy2 binds a non-extended WKBElement by converting it
        # through Shapely, which does not support M (4th dimension)
        # coordinates and silently drops them. A WKBElement built from real
        # EWKB is detected as already-extended and bound as a hex string
        # directly instead, preserving all dimensions.
        geometry = _to_ewkb(geometry, srid)
    return from_wkb(geometry, srid)


def _to_ewkb(wkb_bytes, srid):
    byte_order = wkb_bytes[0]
    fmt = '<I' if byte_order == 1 else '>I'
    geom_type = struct.unpack(fmt, wkb_bytes[1:5])[0]
    ewkb_type = geom_type | _EWKB_SRID_FLAG
    return (
        wkb_bytes[0:1]
        + struct.pack(fmt, ewkb_type)
        + struct.pack(fmt, srid)
        + wkb_bytes[5:]
    )


def geojson_from_wkbelement(wkb_element):
    data = bytes(wkb_element.data)
    if is_empty_wkb(data):
        # geomet cannot read empty geometries, answer them like missing ones
        return None
    geometry = wkb.loads(data)
    return geojson.dumps(geometry)


def is_empty_wkb(wkb_bytes):
    """Tell if a (E)WKB geometry is empty, e.g. `MULTILINESTRING Z EMPTY`."""
    fmt = '<' if wkb_bytes[0] == 1 else '>'
    geom_type = struct.unpack(fmt + 'I', wkb_bytes[1:5])[0]
    offset = 9 if geom_type & _EWKB_SRID_FLAG else 5
    if (geom_type & 0x0FFFFFFF) % 1000 == 1:
        # an empty point is stored with NaN coordinates
        x, y = struct.unpack(fmt + 'dd', wkb_bytes[offset : offset + 16])
        return math.isnan(x) and math.isnan(y)
    # other types start with their number of points, rings or parts
    return struct.unpack(fmt + 'I', wkb_bytes[offset : offset + 4])[0] == 0


def from_wkb(wkb, srid=-1):
    return WKBElement(memoryview(wkb), srid=srid)
