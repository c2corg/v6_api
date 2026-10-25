"""Conversions between GeoJSON and the WKB of the geometry columns."""

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
    geometry = wkb.loads(bytes(wkb_element.data))
    return geojson.dumps(geometry)


def from_wkb(wkb, srid=-1):
    return WKBElement(memoryview(wkb), srid=srid)
