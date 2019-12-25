# Inspired from the c2cgeoform colander extension
# https://github.com/camptocamp/c2cgeoform/blob/master/c2cgeoform/ext/

from colander import (null, Invalid, SchemaType)

from geoalchemy2 import WKBElement
from geomet import wkb
from geoalchemy2.compat import buffer, bytes
import geojson


# import from geojson
def _is_polygon(coords):
    lengths = all(len(elem) >= 4 for elem in coords)
    isring = all(elem[0] == elem[-1] for elem in coords)
    return lengths and isring


def _checkListOfObjects(coord, pred):  # noqa
    """ This method provides checking list of geojson objects such Multipoint or
        MultiLineString that each element of the list is valid geojson object.
        This is helpful method for IsValid.
    :param coord: List of coordinates
    :type coord: list
    :param pred: Predicate to check validation of each member in the coord
    :type pred: function
    :return: True if list contains valid objects, False otherwise
    :rtype: bool
    """
    return not isinstance(coord, list) or not all([pred(ls) for ls in coord])


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
    def __init__(self, geometry_types=['GEOMETRY'], srid=-1, map_srid=-1):
        self.geometry_types = [t.upper() for t in geometry_types]
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
            data = geojson.loads(cstruct)
        except Invalid as exc:
            raise exc
        except:  # noqa
            raise Invalid(node, 'Invalid geometry: %s' % cstruct)
        if not isinstance(data, geojson.GeoJSON):
            raise Invalid(node, 'Invalid geometry: %s' % cstruct)
        geom_type = data['type'].upper()
        allowed_types = self.geometry_types
        if geom_type in allowed_types:
            if not is_valid_geometry(data):
                raise Invalid(node, 'Invalid geometry: %s' % cstruct)
            else:
                return wkbelement_from_geojson(data, self.srid)
        else:
            raise Invalid(
                node, 'Invalid geometry type. Expected: %s. Got: %s.'
                % (allowed_types, geom_type))

    def cstruct_children(self, node, cstruct):
        return []


def wkbelement_from_geojson(geojson, srid):
    geometry = wkb.dumps(geojson, big_endian=False)
    return from_wkb(geometry, srid)


def geojson_from_wkbelement(wkb_element):
    geometry = wkb.loads(bytes(wkb_element.data))
    return geojson.dumps(geometry)


def from_wkb(wkb, srid=-1):
    return WKBElement(buffer(wkb), srid=srid)


def is_valid_geometry(obj):
    """
    Adapted from geojson.is_valid()
    https://github.com/frewsxcv/python-geojson/blob/master/geojson/validation.py
    """

    if isinstance(obj, geojson.Point) and \
            len(obj['coordinates']) not in (2, 3):
        # Points have 2 or 3 dimensions
        return False

    # MultiPoint type is not handled because else 4D linestrings are
    # incorrectly detected as multipoints

    if isinstance(obj, geojson.LineString) and \
            len(obj['coordinates']) < 2:
        # Lines must have at least 2 positions
        return False

    if isinstance(obj, geojson.MultiLineString) and \
            _checkListOfObjects(obj['coordinates'], lambda x: len(x) >= 2):
        # Each segment must must have at least 2 positions
        return False

    if isinstance(obj, geojson.Polygon):
        coord = obj['coordinates']
        lengths = all([len(elem) >= 4 for elem in coord])
        if lengths is False:
            # LinearRing must contain 4 or more positions
            return False

        isring = all([elem[0] == elem[-1] for elem in coord])
        if isring is False:
            # The first and last positions in LinearRing must be equivalent
            return False

        return True

    if isinstance(obj, geojson.MultiPolygon) and \
            _checkListOfObjects(obj['coordinates'], lambda x: _is_polygon(x)):
        # the "coordinates" member must be an array
        # of Polygon coordinate arrays
        return False

    return True
