import unittest

from c2corg_api.fields_waypoint import fields_waypoint
from c2corg_api.attributes import waypoint_types
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.document import DocumentGeometry


class TestFields(unittest.TestCase):

    def test_waypoint_fields(self):
        """Test that the fields listed for a waypoint type are correct.
        """
        for type in fields_waypoint:
            self.assertIn(
                type, waypoint_types, 'invalid waypoint type: %s' % (type))
            self._test_fields_for_type(type)

    def _test_fields_for_type(self, waypoint_type):
        fields_info = fields_waypoint.get(waypoint_type)
        self._test_fields(fields_info.get('fields'))
        self._test_fields(fields_info.get('required'))

    def _test_fields(self, fields):
        for field in fields:
            if '.' in field:
                field_parts = field.split('.')
                self.assertEquals(
                    len(field_parts), 2, 'only checking the next level')
                self.assertTrue(
                    hasattr(Waypoint, field_parts[0]),
                    '%s in %s' % (field_parts[0], Waypoint))

                if field_parts[0] == 'locales':
                    model = WaypointLocale
                elif field_parts[0] == 'geometry':
                    model = DocumentGeometry
                else:
                    self.assertTrue(
                        False, '%s not expected' % (field_parts[0]))
                self.assertTrue(
                    hasattr(model, field_parts[1]),
                    '%s not in %s' % (field_parts[1], model))
            else:
                self.assertTrue(
                    hasattr(Waypoint, field),
                    '%s not in %s' % (field, Waypoint))
