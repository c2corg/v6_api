from c2corg_api.models.waypoint import Waypoint, WaypointLocale

from c2corg_api.tests import BaseTestCase

from sqlalchemy.orm.exc import StaleDataError

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

    def test_version_is_incremented(self):
        waypoint = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc')
            ]
        )
        self.session.add(waypoint)
        self.session.flush()

        version1 = waypoint.version
        self.assertIsNotNone(version1)

        # make a change to the waypoint and check that the version changes
        # once the waypoint is persisted
        waypoint.elevation = 1234
        self.session.merge(waypoint)
        self.session.flush()
        version2 = waypoint.version
        self.assertNotEqual(version1, version2)

    def test_version_concurrent_edit(self):
        """Test that a `StaleDataError` is thrown when trying to update a
        waypoint with an old version number.
        """
        waypoint1 = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc')
            ]
        )

        # add the initial waypoint
        self.session.add(waypoint1)
        self.session.flush()
        self.session.expunge(waypoint1)
        version1 = waypoint1.version
        self.assertIsNotNone(version1)

        # change the waypoint
        waypoint2 = self.session.query(Waypoint).get(waypoint1.document_id)
        waypoint2.elevation = 1234
        self.session.merge(waypoint2)
        self.session.flush()
        version2 = waypoint2.version
        self.assertNotEqual(version1, version2)

        self.assertNotEqual(waypoint1.version, waypoint2.version)
        self.assertNotEqual(waypoint1.elevation, waypoint2.elevation)

        # then try to update the waypoint again with the old version
        waypoint1.elevation = 2345
        self.assertRaises(StaleDataError, self.session.merge, waypoint1)
