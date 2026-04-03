"""Tests for c2corg_api.models.objectify — standalone objectify replacement."""
import unittest

from c2corg_api.models.objectify import objectify, _get_locale_class

from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.models.image import Image
from c2corg_api.models.book import Book
from c2corg_api.models.article import Article
from c2corg_api.models.area import Area
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.ext.geometry import wkbelement_from_geojson

from geoalchemy2 import WKBElement


class TestGetLocaleClass(unittest.TestCase):

    def test_route_locale_class(self):
        self.assertIs(_get_locale_class(Route), RouteLocale)

    def test_waypoint_locale_class(self):
        self.assertIs(_get_locale_class(Waypoint), WaypointLocale)

    def test_outing_locale_class(self):
        self.assertIs(_get_locale_class(Outing), OutingLocale)

    def test_xreport_locale_class(self):
        self.assertIs(_get_locale_class(Xreport), XreportLocale)

    def test_image_locale_class(self):
        self.assertIs(_get_locale_class(Image), DocumentLocale)

    def test_book_locale_class(self):
        self.assertIs(_get_locale_class(Book), DocumentLocale)

    def test_article_locale_class(self):
        self.assertIs(_get_locale_class(Article), DocumentLocale)

    def test_area_locale_class(self):
        self.assertIs(_get_locale_class(Area), DocumentLocale)

    def test_user_profile_locale_class(self):
        self.assertIs(_get_locale_class(UserProfile), DocumentLocale)

    def test_non_document_model(self):
        """User is not a polymorphic document; no locale class."""
        self.assertIsNone(_get_locale_class(User))


class TestObjectifyScalar(unittest.TestCase):

    def test_user_flat(self):
        data = {
            'username': 'test_user',
            'name': 'Test',
            'forum_username': 'test_forum',
            'email': 'test@example.com',
            'lang': 'en',
        }
        user = objectify(User, data)
        self.assertIsInstance(user, User)
        self.assertEqual(user.username, 'test_user')
        self.assertEqual(user.name, 'Test')
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.lang, 'en')

    def test_ignores_unknown_keys(self):
        data = {
            'username': 'u',
            'unknown_field': 'ignored',
            'associations': {'routes': [{'document_id': 1}]},
        }
        user = objectify(User, data)
        self.assertEqual(user.username, 'u')
        self.assertFalse(hasattr(user, 'unknown_field'))

    def test_none_scalar_is_set(self):
        data = {'username': 'u', 'name': None}
        user = objectify(User, data)
        self.assertIsNone(user.name)


class TestObjectifyDocument(unittest.TestCase):

    def test_route_with_locales(self):
        data = {
            'document_id': None,
            'activities': ['skitouring'],
            'elevation_min': 1500,
            'elevation_max': 3000,
            'locales': [
                {
                    'lang': 'fr',
                    'title': 'Col de la Vanoise',
                    'title_prefix': 'Course',
                },
                {
                    'lang': 'en',
                    'title': 'Col de la Vanoise',
                },
            ],
        }
        route = objectify(Route, data)
        self.assertIsInstance(route, Route)
        self.assertEqual(route.activities, ['skitouring'])
        self.assertEqual(route.elevation_min, 1500)
        self.assertEqual(len(route.locales), 2)
        # Must be RouteLocale, not plain DocumentLocale
        for locale in route.locales:
            self.assertIsInstance(locale, RouteLocale)
        self.assertEqual(route.locales[0].lang, 'fr')
        self.assertEqual(route.locales[0].title_prefix, 'Course')

    def test_waypoint_with_geometry(self):
        geom_wkb = wkbelement_from_geojson(
            {"type": "Point", "coordinates": [6.0, 45.0]}, 3857)
        data = {
            'document_id': None,
            'waypoint_type': 'summit',
            'elevation': 4000,
            'geometry': {
                'geom': geom_wkb,
            },
            'locales': [
                {
                    'lang': 'en',
                    'title': 'Mont Blanc',
                },
            ],
        }
        wp = objectify(Waypoint, data)
        self.assertIsInstance(wp, Waypoint)
        self.assertEqual(wp.waypoint_type, 'summit')
        self.assertIsInstance(wp.geometry, DocumentGeometry)
        self.assertIsInstance(wp.geometry.geom, WKBElement)
        self.assertEqual(len(wp.locales), 1)
        self.assertIsInstance(wp.locales[0], WaypointLocale)
        self.assertEqual(wp.locales[0].title, 'Mont Blanc')

    def test_outing_locale_class(self):
        data = {
            'locales': [{'lang': 'fr', 'title': 'Sortie test'}],
        }
        outing = objectify(Outing, data)
        self.assertIsInstance(outing.locales[0], OutingLocale)

    def test_xreport_locale_class(self):
        data = {
            'locales': [{'lang': 'fr', 'title': 'Accident test'}],
        }
        xr = objectify(Xreport, data)
        self.assertIsInstance(xr.locales[0], XreportLocale)

    def test_image_uses_document_locale(self):
        data = {
            'locales': [{'lang': 'fr', 'title': 'Photo test'}],
        }
        img = objectify(Image, data)
        self.assertIsInstance(img.locales[0], DocumentLocale)

    def test_empty_geometry_skipped(self):
        """When geometry is None it should not create a DocumentGeometry."""
        data = {
            'waypoint_type': 'summit',
            'elevation': 1000,
            'geometry': None,
            'locales': [{'lang': 'en', 'title': 'Peak'}],
        }
        wp = objectify(Waypoint, data)
        # geometry should remain the default (None), not a
        # DocumentGeometry instance
        self.assertIsNone(wp.geometry)


if __name__ == '__main__':
    unittest.main()
