from colander import (null, Invalid)
from geoalchemy2 import WKBElement
from geoalchemy2.shape import to_shape, from_shape
import json
import unittest


class TestGeometry(unittest.TestCase):

    def test_serialize_null(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertEquals(null, geom_schema.serialize({}, null))

    def test_serialize_wkb(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        from shapely.geometry.point import Point
        wkb = from_shape(Point(1.0, 2.0))
        self.assertEquals(
            '{"type": "Point", "coordinates": [1.0, 2.0]}',
            geom_schema.serialize({}, wkb))

    def test_serialize_reproject(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry(srid=4326, map_srid=3857)

        from shapely.geometry.point import Point
        wkb = from_shape(Point(1.0, 2.0), 4326)
        geo_json = json.loads(geom_schema.serialize({}, wkb))
        self.assertEquals('Point', geo_json['type'])
        self.assertAlmostEqual(111319.49079327231, geo_json['coordinates'][0])
        self.assertAlmostEqual(222684.20850554455, geo_json['coordinates'][1])

    def test_serialize_invalid(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertRaises(
            Invalid,
            geom_schema.serialize, {}, 'Point(1 0)')

    def test_deserialize_null(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertEquals(null, geom_schema.deserialize({}, null))
        self.assertEquals(null, geom_schema.deserialize({}, ''))

    def test_deserialize_valid_geojson(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        from shapely.geometry.point import Point
        expected_wkb = WKBElement(Point(1.0, 2.0).wkb)

        wkb = geom_schema.deserialize(
            {}, '{"type": "Point", "coordinates": [1.0, 2.0]}')
        self.assertEquals(expected_wkb.desc, wkb.desc)

    def test_deserialize_reproject(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry(srid=4326, map_srid=3857)

        wkb = geom_schema.deserialize(
            {},
            '{"type": "Point", '
            '"coordinates": [111319.49079327231, 222684.20850554455]}')
        self.assertEquals(4326, wkb.srid)

        shape = to_shape(wkb)
        self.assertAlmostEqual(1.0, shape.x)
        self.assertAlmostEqual(2.0, shape.y)

    def test_serialize_invalid_wrong_type(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertRaises(
            Invalid,
            geom_schema.deserialize,
            {},
            '{"type": "InvalidType", "coordinates": [1.0, 2.0]}')

    def test_serialize_invalid_syntax(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertRaises(
            Invalid,
            geom_schema.deserialize,
            {},
            '"type": "Point", "coordinates": [1.0, 2.0]}')
