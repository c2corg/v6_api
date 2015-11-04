import unittest

from c2corg_common.fields_waypoint import fields_waypoint
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.waypoint import schema_waypoint


class TestUtils(unittest.TestCase):

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
        self.assertHasField(locale_node, 'culture')
        self.assertHasField(locale_node, 'title')
        self.assertHasNotField(locale_node, 'access_period')

    def get_child_node(self, node, name):
        return next(
            (child for child in node.children if child.name == name), None)

    def assertHasField(self, node, name):  # noqa
        self.assertIsNotNone(self.get_child_node(node, name))

    def assertHasNotField(self, node, name):  # noqa
        self.assertIs(self.get_child_node(node, name), None)
