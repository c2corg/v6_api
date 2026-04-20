import json

import pytest

from c2corg_api.ext.geometry import wkbelement_from_geojson
from c2corg_api.models.common.fields_waypoint import fields_waypoint
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.models.waypoint import schema_waypoint


class TestUtils:
    def test_restrict_schema(self):
        fields = fields_waypoint.get('summit').get('fields')
        restricted = schema_waypoint.restrict(fields)

        assert 'document_id' in restricted.columns
        assert 'version' in restricted.columns
        assert 'elevation' in restricted.columns
        assert 'climbing_outdoor_types' not in restricted.columns

        # geometry fields should be present
        assert restricted.geometry_fields is not None
        assert 'version' in restricted.geometry_fields
        assert 'geom' in restricted.geometry_fields

        # locale fields should be present with defaults
        assert restricted.locale_fields is not None
        assert 'version' in restricted.locale_fields
        assert 'lang' in restricted.locale_fields
        assert 'title' in restricted.locale_fields
        assert 'access_period' not in restricted.locale_fields

    def test_wkb_to_shape_point(self):
        wkb = wkbelement_from_geojson(
            json.loads('{"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]}'), 3857
        )
        point = wkb_to_shape(wkb)
        assert not point.has_z
        assert point.x == pytest.approx(1.0)
        assert point.y == pytest.approx(2.0)

    def test_wkb_to_shape_linestring(self):
        wkb = wkbelement_from_geojson(
            json.loads(
                '{"type": "LineString", "coordinates": '
                + '[[635956, 5723604, 1200], [635966, 5723644, 1210]]}'
            ),
            3857,
        )
        line = wkb_to_shape(wkb)
        assert not line.has_z

        assert len(line.coords) == 2
        assert len(line.coords[0]) == 2
        assert len(line.coords[1]) == 2
        assert [635956.0, 5723604.0] == pytest.approx(line.coords[0])
        assert [635966.0, 5723644.0] == pytest.approx(line.coords[1])

    def test_wkb_to_shape_multilinestring(self):
        wkb = wkbelement_from_geojson(
            json.loads(
                '{"type": "MultiLineString", "coordinates": '
                + '[[[635956, 5723604, 1200], [635966, 5723644, 1210]]]}'
            ),
            3857,
        )
        line = wkb_to_shape(wkb)
        assert not line.has_z

        assert len(line.geoms) == 1
        assert len(line.geoms[0].coords) == 2
        assert len(line.geoms[0].coords[0]) == 2
        assert [635956.0, 5723604.0] == pytest.approx(line.geoms[0].coords[0])
        assert [635966.0, 5723644.0] == pytest.approx(line.geoms[0].coords[1])

    def test_wkb_to_shape_polygon(self):
        wkb = wkbelement_from_geojson(
            json.loads(
                '{"type": "Polygon", "coordinates": '
                + '[[[100.0, 0.0, 1200], [101.0, 0.0, 1200], [101.0, 1.0, 1200], '
                '[100.0, 1.0, 1200], [100.0, 0.0, 1200]]]}'
            ),
            3857,
        )
        polygon = wkb_to_shape(wkb)
        assert not polygon.has_z

        assert len(polygon.exterior.coords) == 5
        assert len(polygon.exterior.coords[0]) == 2

    def test_wkb_to_shape_multipolygon(self):
        wkb = wkbelement_from_geojson(
            json.loads(
                '{"type": "MultiPolygon", "coordinates": '
                + '[[[[100.0, 0.0, 1200], [101.0, 0.0, 1200], [101.0, 1.0, 1200], '
                '[100.0, 1.0, 1200], [100.0, 0.0, 1200]]]]}'
            ),
            3857,
        )
        multi_polygon = wkb_to_shape(wkb)
        assert not multi_polygon.has_z

        assert len(multi_polygon.geoms[0].exterior.coords) == 5
        assert len(multi_polygon.geoms[0].exterior.coords[0]) == 2
