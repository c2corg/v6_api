from c2corg_api.ext.geometry import (
    wkbelement_from_geojson,
    geojson_from_wkbelement,
)
from c2corg_api.models.document import DocumentGeometry, Document
from c2corg_api.tests import BaseTestCase
import json


class TestGeometry(BaseTestCase):

    def test_save_and_load(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            json.loads('{"type": "Point", "coordinates": [1.0, 2.0]}'), 3857
        )
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom=geom
        )
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals([1.0, 2.0], geom_geojson["coordinates"])

    def test_save_and_load_3d(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            json.loads('{"type": "Point", "coordinates": [1.0, 2.0, 3.0]}'),
            3857,
        )
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom_detail=geom
        )
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom_detail
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals(
            [1.0, 2.0, 3.0], geom_geojson["coordinates"]
        )

    def test_save_and_load_4d(self):
        fake_doc = Document()
        self.session.add(fake_doc)
        self.session.flush()

        geom = wkbelement_from_geojson(
            json.loads(
                '{"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]}'
            ),
            3857,
        )
        geometry = DocumentGeometry(
            document_id=fake_doc.document_id, geom_detail=geom
        )
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)

        geom_loaded = geometry.geom_detail
        geom_str = geojson_from_wkbelement(geom_loaded)

        geom_geojson = json.loads(geom_str)
        self.assertCoodinateEquals(
            [1.0, 2.0, 3.0, 4.0], geom_geojson["coordinates"]
        )
