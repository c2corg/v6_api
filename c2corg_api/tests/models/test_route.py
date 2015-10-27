from c2corg_api.models.route import Route, RouteLocale

from c2corg_api.tests import BaseTestCase


class TestRoute(BaseTestCase):

    def test_to_archive(self):
        route = Route(
            document_id=1, route_type='ski', activities=['skitouring'],
            elevation_max=1200,
            locales=[
                RouteLocale(
                    id=2, culture='en', title='A', description='abc',
                    gear='...'),
                RouteLocale(
                    id=3, culture='fr', title='B', description='bcd',
                    gear='...'),
            ]
        )

        route_archive = route.to_archive()

        self.assertIsNone(route_archive.id)
        self.assertEqual(route_archive.document_id, route.document_id)
        self.assertEqual(route_archive.route_type, route.route_type)
        self.assertEqual(
            route_archive.activities, route.activities)
        self.assertEqual(route_archive.elevation_max, route.elevation_max)

        archive_locals = route.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = route.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.culture, locale.culture)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
        self.assertEqual(locale_archive.gear, locale.gear)
