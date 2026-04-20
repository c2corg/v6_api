"""Tests for c2corg_api.models.objectify — standalone objectify replacement."""

import unittest

from geoalchemy2 import WKBElement

from c2corg_api.ext.geometry import wkbelement_from_geojson
from c2corg_api.models.area import Area
from c2corg_api.models.article import Article
from c2corg_api.models.book import Book
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.image import Image
from c2corg_api.models.objectify import _get_locale_class, objectify
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.xreport import Xreport, XreportLocale


class TestGetLocaleClass:
    def test_route_locale_class(self):
        assert _get_locale_class(Route) is RouteLocale

    def test_waypoint_locale_class(self):
        assert _get_locale_class(Waypoint) is WaypointLocale

    def test_outing_locale_class(self):
        assert _get_locale_class(Outing) is OutingLocale

    def test_xreport_locale_class(self):
        assert _get_locale_class(Xreport) is XreportLocale

    def test_image_locale_class(self):
        assert _get_locale_class(Image) is DocumentLocale

    def test_book_locale_class(self):
        assert _get_locale_class(Book) is DocumentLocale

    def test_article_locale_class(self):
        assert _get_locale_class(Article) is DocumentLocale

    def test_area_locale_class(self):
        assert _get_locale_class(Area) is DocumentLocale

    def test_user_profile_locale_class(self):
        assert _get_locale_class(UserProfile) is DocumentLocale

    def test_non_document_model(self):
        """User is not a polymorphic document; no locale class."""
        assert _get_locale_class(User) is None


class TestObjectifyScalar:
    def test_user_flat(self):
        data = {
            'username': 'test_user',
            'name': 'Test',
            'forum_username': 'test_forum',
            'email': 'test@example.com',
            'lang': 'en',
        }
        user = objectify(User, data)
        assert isinstance(user, User)
        assert user.username == 'test_user'
        assert user.name == 'Test'
        assert user.email == 'test@example.com'
        assert user.lang == 'en'

    def test_ignores_unknown_keys(self):
        data = {
            'username': 'u',
            'unknown_field': 'ignored',
            'associations': {'routes': [{'document_id': 1}]},
        }
        user = objectify(User, data)
        assert user.username == 'u'
        assert not hasattr(user, 'unknown_field')

    def test_none_scalar_is_set(self):
        data = {'username': 'u', 'name': None}
        user = objectify(User, data)
        assert user.name is None


class TestObjectifyDocument:
    def test_route_with_locales(self):
        data = {
            'document_id': None,
            'activities': ['skitouring'],
            'elevation_min': 1500,
            'elevation_max': 3000,
            'locales': [
                {'lang': 'fr', 'title': 'Col de la Vanoise', 'title_prefix': 'Course'},
                {'lang': 'en', 'title': 'Col de la Vanoise'},
            ],
        }
        route = objectify(Route, data)
        assert isinstance(route, Route)
        assert route.activities == ['skitouring']
        assert route.elevation_min == 1500
        assert len(route.locales) == 2
        # Must be RouteLocale, not plain DocumentLocale
        for locale in route.locales:
            assert isinstance(locale, RouteLocale)
        assert route.locales[0].lang == 'fr'
        assert route.locales[0].title_prefix == 'Course'

    def test_waypoint_with_geometry(self):
        geom_wkb = wkbelement_from_geojson(
            {'type': 'Point', 'coordinates': [6.0, 45.0]}, 3857
        )
        data = {
            'document_id': None,
            'waypoint_type': 'summit',
            'elevation': 4000,
            'geometry': {'geom': geom_wkb},
            'locales': [{'lang': 'en', 'title': 'Mont Blanc'}],
        }
        wp = objectify(Waypoint, data)
        assert isinstance(wp, Waypoint)
        assert wp.waypoint_type == 'summit'
        assert isinstance(wp.geometry, DocumentGeometry)
        assert isinstance(wp.geometry.geom, WKBElement)
        assert len(wp.locales) == 1
        assert isinstance(wp.locales[0], WaypointLocale)
        assert wp.locales[0].title == 'Mont Blanc'

    def test_outing_locale_class(self):
        data = {'locales': [{'lang': 'fr', 'title': 'Sortie test'}]}
        outing = objectify(Outing, data)
        assert isinstance(outing.locales[0], OutingLocale)

    def test_xreport_locale_class(self):
        data = {'locales': [{'lang': 'fr', 'title': 'Accident test'}]}
        xr = objectify(Xreport, data)
        assert isinstance(xr.locales[0], XreportLocale)

    def test_image_uses_document_locale(self):
        data = {'locales': [{'lang': 'fr', 'title': 'Photo test'}]}
        img = objectify(Image, data)
        assert isinstance(img.locales[0], DocumentLocale)

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
        assert wp.geometry is None


if __name__ == '__main__':
    unittest.main()
