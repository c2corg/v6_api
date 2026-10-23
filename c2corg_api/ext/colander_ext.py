# Inspired from the c2cgeoform colander extension
# https://github.com/camptocamp/c2cgeoform/blob/master/c2cgeoform/ext/

import struct
from numbers import Number

import geojson
from colander import Invalid, SchemaType, null
from geoalchemy2 import WKBElement
from geomet import wkb

# EWKB SRID flag, see https://git.osgeo.org/gitea/postgis/postgis/raw/
# master/doc/ZMSgeoms.txt
_EWKB_SRID_FLAG = 0x20000000


class Geometry(SchemaType):
    """Colander type for GeoAlchemy 2 geometry columns.

    A Colander type meant to be used with GeoAlchemy 2 geometry columns.
    Example usage
    .. code-block:: python
        geom = Column(
            geoalchemy2.Geometry('POLYGON', 4326, management=True), info={
                'colanderalchemy': {
                    'typ': colander_ext.Geometry(
                        'POLYGON', srid=4326, map_srid=3857),
                    'widget': deform_ext.MapWidget()
                }})
    **Attributes/Arguments**
    geometry_type
        The geometry type should match the column geometry type.
    srid
        The SRID of the geometry should also match the column definition.
    """

    def __init__(self, geometry_types=('GEOMETRY',), srid=-1, map_srid=-1):
        self.geometry_types = [t.upper() for t in geometry_types]
        self.srid = int(srid)

    def serialize(self, node, appstruct):
        """Convert a `WKBElement` (appstruct) into a GeoJSON string (cstruct).

        In Colander speak: Converts a Python data structure (an appstruct) into
        a serialization (a cstruct).
        Or: Converts a `WKBElement` into a GeoJSON string.
        """
        if appstruct is null:
            return null
        if isinstance(appstruct, WKBElement):
            return geojson_from_wkbelement(appstruct)

        raise Invalid(node, f'Unexpected value: {appstruct!r}')

    def deserialize(self, node, cstruct):
        """Convert a GeoJSON string (cstruct) into a `WKBElement` (appstruct).

        In Colander speak: Converts a serialized value (a cstruct) into a
        Python data structure (a appstruct).
        Or: Converts a GeoJSON string into a `WKBElement`.
        """
        if cstruct is null or cstruct == '':
            return null
        try:
            data = geojson.loads(cstruct)
        except Invalid as exc:
            raise exc
        except Exception as e:
            raise Invalid(node, f'Invalid geometry: {cstruct}') from e
        if not isinstance(data, geojson.GeoJSON):
            raise Invalid(node, f'Invalid geometry: {cstruct}')
        geom_type = data['type'].upper()
        allowed_types = self.geometry_types
        if geom_type in allowed_types:
            if not is_valid_geometry(data):
                raise Invalid(node, f'Invalid geometry: {cstruct}')
            else:
                return wkbelement_from_geojson(data, self.srid)
        else:
            raise Invalid(
                node,
                f'Invalid geometry type. Expected: {allowed_types}. Got: {geom_type}.',
            )

    def cstruct_children(self, node, cstruct):
        return []


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
