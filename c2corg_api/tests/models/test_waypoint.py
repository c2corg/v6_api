from c2corg_api.models.waypoint import Waypoint, WaypointLocale

from c2corg_api.tests import BaseTestCase


class TestWaypoint(BaseTestCase):

    def test_to_archive(self):
        waypoint = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc'),
                WaypointLocale(
                    id=3, culture='fr', title='B', description='bcd'),
            ]
        )

        waypoint_archive = waypoint.to_archive()

        self.assertIsNone(waypoint_archive.id)
        self.assertEqual(waypoint_archive.document_id, waypoint.document_id)
        self.assertEqual(
            waypoint_archive.waypoint_type, waypoint.waypoint_type)
        self.assertEqual(waypoint_archive.elevation, waypoint.elevation)

        archive_locals = waypoint.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = waypoint.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.culture, locale.culture)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
