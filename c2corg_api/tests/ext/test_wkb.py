import json

from c2corg_api.ext.wkb import geojson_from_wkbelement, wkbelement_from_geojson
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.tests import BaseTestCase


class TestWkb(BaseTestCase):
    def _save_and_load(self, geojson, field):
        document = Document()
        self.session.add(document)
        self.session.flush()
        geometry = DocumentGeometry(
            document_id=document.document_id,
            **{field: wkbelement_from_geojson(json.loads(geojson), 3857)},
        )
        self.session.add(geometry)
        self.session.flush()
        self.session.expire(geometry)
        return json.loads(geojson_from_wkbelement(getattr(geometry, field)))

    def test_save_and_load(self):
        loaded = self._save_and_load('{"type": "Point", "coordinates": [1, 2]}', 'geom')
        self.assertCoodinateEquals([1.0, 2.0], loaded['coordinates'])

    def test_save_and_load_3d(self):
        loaded = self._save_and_load(
            '{"type": "Point", "coordinates": [1, 2, 3]}', 'geom_detail'
        )
        self.assertCoodinateEquals([1.0, 2.0, 3.0], loaded['coordinates'])

    def test_save_and_load_4d(self):
        # the 4th dimension (time of GPS tracks) must survive the database
        loaded = self._save_and_load(
            '{"type": "Point", "coordinates": [1, 2, 3, 4]}', 'geom_detail'
        )
        self.assertCoodinateEquals([1.0, 2.0, 3.0, 4.0], loaded['coordinates'])
