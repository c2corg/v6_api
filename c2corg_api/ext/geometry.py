# Geometry serialisation utilities (WKB ↔ GeoJSON).
# Originally inspired from the c2cgeoform geometry extension.

from geoalchemy2 import WKBElement
from geomet import wkb
import geojson
import struct
from numbers import Number

# PostGIS EWKB bitmask flags
_EWKB_Z_FLAG = 0x80000000
_EWKB_M_FLAG = 0x40000000
_EWKB_SRID_FLAG = 0x20000000


def wkbelement_from_geojson(geojson_data, srid):
    geometry = wkb.dumps(geojson_data, big_endian=False)
    return from_wkb(geometry, srid)


def geojson_from_wkbelement(wkb_element):
    data = wkb_element.data
    if isinstance(data, memoryview):
        data = bytes(data)
    elif isinstance(data, str):
        data = bytes.fromhex(data)
    data = _ewkb_to_iso_wkb(data)
    geometry = wkb.loads(data)
    return geojson.dumps(geometry)


def _ewkb_to_iso_wkb(data):
    """Convert PostGIS EWKB to ISO WKB that geomet can parse.

    PostGIS EWKB encodes Z/M/SRID as bitmask flags in the type integer
    (0x80000000 for Z, 0x40000000 for M, 0x20000000 for SRID).
    ISO WKB uses type code offsets (+1000 for Z, +2000 for M, +3000 for ZM).

    This function handles compound geometries (Multi*, GeometryCollection)
    by recursively converting each sub-geometry header.
    """
    result = bytearray()
    _ewkb_to_iso_wkb_at(data, 0, result)
    return bytes(result)


# Number of coordinates per point for each dimension combo
_COORDS_PER_POINT = {
    (False, False): 2,  # 2D
    (True, False): 3,   # Z
    (False, True): 3,   # M
    (True, True): 4,    # ZM
}

# WKB base type -> whether it's a multi/collection type
_MULTI_TYPES = {4, 5, 6, 7}  # MultiPoint, MultiLS, MultiPoly, GeomCollection


def _ewkb_to_iso_wkb_at(data, offset, result):
    """Convert one geometry starting at `offset`, appending ISO WKB to result.
    Returns the new offset past the consumed bytes.
    """
    if offset + 5 > len(data):
        # Not enough data; copy remainder as-is
        result.extend(data[offset:])
        return len(data)

    byte_order = data[offset]
    fmt = '<I' if byte_order == 1 else '>I'
    type_int = struct.unpack_from(fmt, data, offset + 1)[0]

    has_srid = bool(type_int & _EWKB_SRID_FLAG)
    has_z = bool(type_int & _EWKB_Z_FLAG)
    has_m = bool(type_int & _EWKB_M_FLAG)

    base_type = type_int & 0x0FFFFFFF
    iso_type = base_type
    if has_z and has_m:
        iso_type += 3000
    elif has_z:
        iso_type += 1000
    elif has_m:
        iso_type += 2000

    # Write byte order + ISO type
    result.append(byte_order)
    result.extend(struct.pack(fmt, iso_type))

    # Advance past header (byte_order + type + optional SRID)
    hdr_size = 5 + (4 if has_srid else 0)
    offset += hdr_size

    coords_per_point = _COORDS_PER_POINT[(has_z, has_m)]
    point_size = coords_per_point * 8  # 8 bytes per float64

    if base_type in _MULTI_TYPES:
        # Multi/Collection: read count, then recurse for each sub-geometry
        if offset + 4 > len(data):
            result.extend(data[offset:])
            return len(data)
        count = struct.unpack_from(fmt, data, offset)[0]
        result.extend(struct.pack(fmt, count))
        offset += 4
        for _ in range(count):
            offset = _ewkb_to_iso_wkb_at(data, offset, result)
    elif base_type == 1:
        # Point
        result.extend(data[offset:offset + point_size])
        offset += point_size
    elif base_type == 2:
        # LineString
        if offset + 4 > len(data):
            result.extend(data[offset:])
            return len(data)
        num_points = struct.unpack_from(fmt, data, offset)[0]
        result.extend(struct.pack(fmt, num_points))
        offset += 4
        size = num_points * point_size
        result.extend(data[offset:offset + size])
        offset += size
    elif base_type == 3:
        # Polygon
        if offset + 4 > len(data):
            result.extend(data[offset:])
            return len(data)
        num_rings = struct.unpack_from(fmt, data, offset)[0]
        result.extend(struct.pack(fmt, num_rings))
        offset += 4
        for _ in range(num_rings):
            if offset + 4 > len(data):
                break
            num_points = struct.unpack_from(fmt, data, offset)[0]
            result.extend(struct.pack(fmt, num_points))
            offset += 4
            size = num_points * point_size
            result.extend(data[offset:offset + size])
            offset += size
    else:
        # Unknown type: copy the rest as-is (best effort)
        result.extend(data[offset:])
        offset = len(data)

    return offset


def from_wkb(raw_wkb, srid=-1):
    """Create a WKBElement from ISO WKB bytes, embedding the SRID as EWKB.

    GeoAlchemy2's bind processor for non-extended WKBElements falls back to
    Shapely (which drops 4D coords). By converting to EWKB and marking the
    element as extended, the raw hex is sent directly to PostGIS, preserving
    all dimensions.
    """
    ewkb = _iso_wkb_to_ewkb(raw_wkb, srid)
    return WKBElement(memoryview(ewkb), srid=srid, extended=True)


def _iso_wkb_to_ewkb(data, srid=-1):
    """Convert ISO WKB to PostGIS EWKB, embedding the SRID.

    ISO WKB uses type code offsets (+1000 for Z, +2000 for M, +3000 for ZM).
    PostGIS EWKB uses bitmask flags (0x80000000 Z, 0x40000000 M, 0x20000000
    SRID) and inserts a 4-byte SRID after the type integer.
    """
    if len(data) < 5:
        return data
    byte_order = data[0]
    fmt = '<I' if byte_order == 1 else '>I'
    type_int = struct.unpack_from(fmt, data, 1)[0]

    base_type = type_int % 1000
    offset = type_int // 1000

    ewkb_type = base_type
    if offset == 1:       # Z
        ewkb_type |= _EWKB_Z_FLAG
    elif offset == 2:     # M
        ewkb_type |= _EWKB_M_FLAG
    elif offset == 3:     # ZM
        ewkb_type |= _EWKB_Z_FLAG | _EWKB_M_FLAG

    if srid > 0:
        ewkb_type |= _EWKB_SRID_FLAG
        return (data[0:1] + struct.pack(fmt, ewkb_type) +
                struct.pack(fmt, srid) + data[5:])
    else:
        return data[0:1] + struct.pack(fmt, ewkb_type) + data[5:]


def is_valid_geometry(obj):
    return obj.is_valid


def _check_point_4d(coord):
    if not isinstance(coord, list):
        return 'each position must be a list'
    if len(coord) not in (2, 3, 4):
        return 'a position must have exactly 2, 3 or 4 values'
    for number in coord:
        if not isinstance(number, Number):
            return 'a position cannot have inner positions'


# geojson RFC says that the coordinates should be 2d or 3d and
# that parsers may ignore additional elements.
# geojson raises an error on 4d coordinates (2 or 3 elements expected),
# We override the function to handle 4d coordinates
geojson.geometry.check_point = _check_point_4d
