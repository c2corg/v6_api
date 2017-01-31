import json

from c2corg_api.ext.colander_ext import wkbelement_from_geojson, \
    geojson_from_wkbelement
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale

from c2corg_api.tests import BaseTestCase


class TestRoute(BaseTestCase):

    def test_to_archive(self):
        route = Route(
            document_id=1, activities=['skitouring'],
            elevation_max=1200,
            locales=[
                RouteLocale(
                    id=2, lang='en', title='A', description='abc',
                    gear='...'),
                RouteLocale(
                    id=3, lang='fr', title='B', description='bcd',
                    gear='...'),
            ]
        )

        route_archive = route.to_archive()

        self.assertIsNone(route_archive.id)
        self.assertEqual(route_archive.document_id, route.document_id)
        self.assertEqual(
            route_archive.activities, route.activities)
        self.assertEqual(route_archive.elevation_max, route.elevation_max)

        archive_locals = route.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = route.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
        self.assertEqual(locale_archive.gear, locale.gear)

    def test_geometry_update(self):
        """ Check that geometries are only compared in 2D when updating a
        document.
        """
        geom1 = wkbelement_from_geojson(json.loads(
            '{"type": "LineString", "coordinates": ' +
            '[[635956, 5723604, 1200], [635966, 5723644, 1210]]}'), 3857)
        route_db = Route(
            document_id=1, activities=['hiking'],
            geometry=DocumentGeometry(
                document_id=1, geom=None, geom_detail=geom1)
        )

        geom2 = wkbelement_from_geojson(json.loads(
            '{"type": "LineString", "coordinates": ' +
            '[[635956, 5723604, 9999], [635966, 5723644, 9999]]}'), 3857)
        route_in = Route(
            document_id=1, activities=['hiking'],
            geometry=DocumentGeometry(
                geom=None, geom_detail=geom2)
        )
        route_db.update(route_in)
        self.assertIs(route_db.geometry.geom_detail, geom1)

        geom3 = wkbelement_from_geojson(json.loads(
            '{"type": "LineString", "coordinates": ' +
            '[[635956, 5723608, 1200], [635966, 5723644, 1210]]}'), 3857)
        route_in = Route(
            document_id=1, activities=['hiking'],
            geometry=DocumentGeometry(
                geom=None, geom_detail=geom3)
        )
        route_db.update(route_in)
        self.assertIsNot(route_db.geometry.geom_detail, geom1)
        self.assertIs(route_db.geometry.geom_detail, geom3)

    def test_simplify(self):
        geom = wkbelement_from_geojson(json.loads(
            '{"type": "LineString", "coordinates": ' +
            '[[635900, 5723600], [635902, 5723600], [635905, 5723600]]}'),
            3857)
        route = Route(
            activities=['hiking'],
            geometry=DocumentGeometry(geom=None, geom_detail=geom))
        self.session.add(route)
        self.session.flush()

        # check that the line was simplified on insertion
        simplified_geom = route.geometry
        self.session.refresh(simplified_geom)
        geojson = json.loads(
            geojson_from_wkbelement(simplified_geom.geom_detail))
        self.assertEqual(len(geojson['coordinates']), 2)

        # check that the line was simplified after an update
        route.geometry.geom_detail = wkbelement_from_geojson(json.loads(
            '{"type": "LineString", "coordinates": ' +
            '[[635901, 5723600], [635902, 5723600], [635905, 5723600]]}'),
            3857)

        self.session.flush()
        simplified_geom = route.geometry
        self.session.refresh(simplified_geom)
        geojson = json.loads(
            geojson_from_wkbelement(simplified_geom.geom_detail))
        self.assertEqual(len(geojson['coordinates']), 2)
        self.assertCoodinateEquals(
            [635901, 5723600], geojson['coordinates'][0])
