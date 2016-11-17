# Inspired from the c2cgeoform colander extension
# https://github.com/camptocamp/c2cgeoform/blob/master/c2cgeoform/ext/

from colander import (null, Invalid, SchemaType)

from geoalchemy2 import WKBElement
from geomet import wkb
from geoalchemy2.compat import buffer, bytes
import json
import geojson


class Geometry(SchemaType):
    """ A Colander type meant to be used with GeoAlchemy 2 geometry columns.
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
    def __init__(self, geometry_type='GEOMETRY', srid=-1, map_srid=-1):
        self.geometry_type = geometry_type.upper()
        self.srid = int(srid)

    def serialize(self, node, appstruct):
        """
        In Colander speak: Converts a Python data structure (an appstruct) into
        a serialization (a cstruct).
        Or: Converts a `WKBElement` into a GeoJSON string.
        """
        if appstruct is null:
            return null
        if isinstance(appstruct, WKBElement):
            return geojson_from_wkbelement(appstruct)

        raise Invalid(node, 'Unexpected value: %r' % appstruct)

    def deserialize(self, node, cstruct):
        """
        In Colander speak: Converts a serialized value (a cstruct) into a
        Python data structure (a appstruct).
        Or: Converts a GeoJSON string into a `WKBElement`.
        """
        if cstruct is null or cstruct == '':
            return null
        try:
            return wkbelement_from_geojson(cstruct, self.srid)
        except Exception:
            raise Invalid(node, 'Invalid geometry: %r' % cstruct)

    def cstruct_children(self, node, cstruct):
        return []


def wkbelement_from_geojson(geojson, srid):
    geometry = wkb.dumps(json.loads(geojson), big_endian=False)
    return from_wkb(geometry, srid)


def geojson_from_wkbelement(wkb_element):
    geometry = wkb.loads(bytes(wkb_element.data))
    return geojson.dumps(geometry)


def from_wkb(wkb, srid=-1):
    return WKBElement(buffer(wkb), srid=srid)
