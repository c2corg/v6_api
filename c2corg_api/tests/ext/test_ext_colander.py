from c2corg_api.ext.colander_ext import from_wkb, wkbelement_from_geojson, \
    geojson_from_wkbelement
from c2corg_api.models.document import DocumentGeometry, Document
from c2corg_api.tests import BaseTestCase
from colander import (null, Invalid)
from geoalchemy2 import WKBElement
from geoalchemy2.shape import from_shape
from geomet import wkb as geomet_wkb
import json


class TestGeometry(BaseTestCase):

    def test_serialize_null(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertEqual(null, geom_schema.serialize({}, null))

    def test_serialize_wkb(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        from shapely.geometry.point import Point
        wkb = from_shape(Point(1.0, 2.0))
        self.assertEqual(
            {"type": "Point", "coordinates": [1.0, 2.0]},
            json.loads(geom_schema.serialize({}, wkb)))

    def test_serialize_4d_wkb(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        wkb = geomet_wkb.dumps(
            {'type': 'Point', 'coordinates': [1.0, 2.0, 3.0, 4.0]},
            big_endian=False)
        self.assertEqual(
            {"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]},
            json.loads(geom_schema.serialize({}, from_wkb(wkb))))

    def test_serialize_invalid(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertRaises(
            Invalid,
            geom_schema.serialize, {}, 'Point(1 0)')

    def test_deserialize_null(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        self.assertEqual(null, geom_schema.deserialize({}, null))
        self.assertEqual(null, geom_schema.deserialize({}, ''))

    def test_deserialize_valid_geojson(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        from shapely.geometry.point import Point
        expected_wkb = WKBElement(Point(1.0, 2.0).wkb)

        wkb = geom_schema.deserialize(
            {}, '{"type": "Point", "coordinates": [1.0, 2.0]}')
        self.assertEqual(expected_wkb.desc, wkb.desc)

    def test_deserialize_4d(self):
        from c2corg_api.ext.colander_ext import Geometry
        geom_schema = Geometry()

        expected_wkb = from_wkb(geomet_wkb.dumps(
            {'type': 'Point', 'coordinates': [1.0, 2.0, 3.0, 4.0]},
            big_endian=False))

        wkb = geom_schema.deserialize(
            {}, '{"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]}')
        self.assertEqual(expected_wkb.desc, wkb.desc)

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

    def test_save_and_load(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            '{"type": "Point", "coordinates": [1.0, 2.0]}', 3857)
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom=geom)
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals([1.0, 2.0], geom_geojson['coordinates'])

    def test_save_and_load_3d(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            '{"type": "Point", "coordinates": [1.0, 2.0, 3.0]}', 3857)
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom_detail=geom)
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom_detail
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals(
            [1.0, 2.0, 3.0], geom_geojson['coordinates'])

    def test_save_and_load_4d(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            '{"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]}', 3857)
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom_detail=geom)
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom_detail
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals(
            [1.0, 2.0, 3.0, 4.0], geom_geojson['coordinates'])
