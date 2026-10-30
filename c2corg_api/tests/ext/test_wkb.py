import json

import pytest
from sqlalchemy import text

from c2corg_api.ext.wkb import (
    geojson_from_wkbelement,
    is_empty_wkb,
    wkbelement_from_geojson,
)
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.utils import wkb_to_shape
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

    def _save_empty_and_load(self, wkt, field):
        # geomet cannot write empty geometries, so store them with PostGIS
        document = Document()
        self.session.add(document)
        self.session.flush()
        self.session.execute(
            text(
                'INSERT INTO guidebook.documents_geometries '
                '(document_id, version, ' + field + ') '
                'VALUES (:id, 1, ST_GeomFromText(:wkt, 3857))'
            ),
            {'id': document.document_id, 'wkt': wkt},
        )
        return self.session.get(DocumentGeometry, document.document_id)

    def test_load_empty(self):
        geometry = self._save_empty_and_load('MULTILINESTRING Z EMPTY', 'geom_detail')
        assert geojson_from_wkbelement(geometry.geom_detail) is None
        assert wkb_to_shape(geometry.geom_detail).is_empty

    def test_load_empty_point(self):
        geometry = self._save_empty_and_load('POINT EMPTY', 'geom')
        assert geojson_from_wkbelement(geometry.geom) is None


@pytest.mark.parametrize(
    ('wkb_hex', 'empty'),
    [
        # MULTILINESTRING Z EMPTY, ISO WKB as read with ST_AsBinary
        ('01ed03000000000000', True),
        # MULTILINESTRING ZM EMPTY (outing 1191283)
        ('01bd0b000000000000', True),
        # the same in EWKB with SRID 3857, as stored
        ('01050000a0110f000000000000', True),
        # GEOMETRYCOLLECTION EMPTY
        ('010700000000000000', True),
        # POINT EMPTY
        ('0101000000000000000000f87f000000000000f87f', True),
        # POINT(1 2)
        ('0101000000000000000000f03f0000000000000040', False),
        # LINESTRING(0 0, 1 1), big endian
        (
            '000000000200000002'
            '00000000000000000000000000000000'
            '3ff00000000000003ff0000000000000',
            False,
        ),
    ],
)
def test_is_empty_wkb(wkb_hex, empty):
    assert is_empty_wkb(bytes.fromhex(wkb_hex)) is empty
