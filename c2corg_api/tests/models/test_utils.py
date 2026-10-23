import json
import unittest

import pytest

from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.common.fields_waypoint import fields_waypoint
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.models.waypoint import schema_waypoint
from c2corg_api.tests import AssertionsMixin


class TestUtils(unittest.TestCase, AssertionsMixin):
    def test_restrict_schema(self):
        fields = fields_waypoint.get('summit').get('fields')
        schema = restrict_schema(schema_waypoint, fields)

        self.assertHasField(schema, 'document_id')
        self.assertHasField(schema, 'version')
        self.assertHasField(schema, 'elevation')
        self.assertHasNotField(schema, 'climbing_outdoor_types')

        geometry_node = self.get_child_node(schema, 'geometry')
        self.assertHasField(geometry_node, 'version')
        self.assertHasField(geometry_node, 'geom')

        locales_node = self.get_child_node(schema, 'locales')
        locale_node = locales_node.children[0]
        self.assertHasField(locale_node, 'version')
        self.assertHasField(locale_node, 'lang')
        self.assertHasField(locale_node, 'title')
        self.assertHasNotField(locale_node, 'access_period')

    def test_wkb_to_shape_point(self):
        wkb = wkbelement_from_geojson(
            json.loads('{"type": "Point", "coordinates": [1.0, 2.0, 3.0, 4.0]}'), 3857
        )
        point = wkb_to_shape(wkb)
        assert not point.has_z
        assert point.x == pytest.approx(1.0, abs=5e-8)
        assert point.y == pytest.approx(2.0, abs=5e-8)

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
        self.assertCoodinateEquals(line.coords[0], [635956.0, 5723604.0])
        self.assertCoodinateEquals(line.coords[1], [635966.0, 5723644.0])

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
        self.assertCoodinateEquals(line.geoms[0].coords[0], [635956.0, 5723604.0])
        self.assertCoodinateEquals(line.geoms[0].coords[1], [635966.0, 5723644.0])

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

    def get_child_node(self, node, name):
        return next((child for child in node.children if child.name == name), None)

    def assertHasField(self, node, name):  # noqa
        assert self.get_child_node(node, name) is not None

    def assertHasNotField(self, node, name):  # noqa
        assert self.get_child_node(node, name) is None
