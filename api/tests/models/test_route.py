from api.models.route import Route, RouteLocale

from .. import BaseTestCase


class TestRoute(BaseTestCase):

    def test_to_archive(self):
        route = Route(
            document_id=1, activities='skitouring', height=1200,
            locales=[
                RouteLocale(
                    id=2, culture='en', title='A', description='abc'),
                RouteLocale(
                    id=3, culture='fr', title='B', description='bcd'),
            ]
        )

        route_archive = route.to_archive()

        self.assertIsNone(route_archive.id)
        self.assertEqual(route_archive.document_id, route.document_id)
        self.assertEqual(
            route_archive.activities, route.activities)
        self.assertEqual(route_archive.height, route.height)

        archive_locals = route.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = route.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.culture, locale.culture)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
