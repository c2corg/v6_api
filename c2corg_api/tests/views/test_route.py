import json
from shapely.geometry import shape, LineString

from c2corg_api.models.route import (
    Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseTestRest


class TestRouteRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/routes", Route, ArchiveRoute, ArchiveRouteLocale)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertNotIn('climbing_outdoor_types', doc)
        self.assertNotIn('elevation_min', doc)

    def test_get_collection_paginated(self):
        self.app.get("/routes?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.route4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.route4.document_id, self.route3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.route3.document_id, self.route2.document_id], 4)

        self.assertResultsEqual(
            self.get_collection(
                {'after': self.route3.document_id, 'limit': 1}),
            [self.route2.document_id], -1)

    def test_get(self):
        body = self.get(self.route)
        self.assertEqual(
            body.get('activities'), self.route.activities)
        self._assert_geometry(body)
        self.assertNotIn('climbing_outdoor_types', body)
        self.assertIn('elevation_min', body)

    def test_get_lang(self):
        self.get_lang(self.route)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertMissing(errors[0], 'activities')

    def test_post_empty_activities_error(self):
        body = self.post_error({
            'activities': []
        })
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'Shorter than minimum length 1')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_invalid_activity(self):
        body_post = {
            'activities': ['cooking'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop'}
            ]
        }
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'invalid value: cooking')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_missing_title(self):
        body_post = {
            'activities': ['skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'culture': 'en'}
            ]
        }
        body = self.post_missing_title(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertRequired(errors[1], 'locales')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'activities': ['hiking'],
            'protected': True,
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom': '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'culture': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body)

        version = doc.versions[0]

        archive_route = version.document_archive
        self.assertEqual(archive_route.activities, ['hiking', 'skitouring'])
        self.assertEqual(archive_route.elevation_max, 1500)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.route.version,
                'activities': ['hiking'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': -9999,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.route.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.route.document_id)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.route.geometry.version,
                    'geom': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635976, 5723654]]}'
                }
            }
        }
        (body, route) = self.put_success_all(body, self.route)

        self.assertEquals(route.elevation_max, 1600)
        locale_en = route.get_locale('en')
        self.assertEquals(locale_en.description, '...')
        self.assertEquals(locale_en.gear, 'none')

        # version with culture 'en'
        versions = route.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')
        self.assertEqual(archive_locale.gear, 'none')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['skitouring'])
        self.assertEqual(archive_document_en.elevation_max, 1600)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with culture 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')
        self.assertEqual(archive_locale.gear, 'paraglider')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)

        self.assertEquals(route.elevation_max, 1600)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, route) = self.put_success_lang_only(body, self.route)

        self.assertEquals(route.get_locale('en').gear, 'none')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'culture': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...', 'gear': 'si'}
                ]
            }
        }
        (body, route) = self.put_success_new_lang(body, self.route)

        self.assertEquals(route.get_locale('es').gear, 'si')

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom'))

        geom = geometry.get('geom')
        line = shape(json.loads(geom))
        self.assertIsInstance(line, LineString)
        self.assertAlmostEqual(line.coords[0][0], 635956)
        self.assertAlmostEqual(line.coords[0][1], 5723604)
        self.assertAlmostEqual(line.coords[1][0], 635966)
        self.assertAlmostEqual(line.coords[1][1], 5723644)

    def _add_test_data(self):
        self.route = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1')

        self.locale_en = RouteLocale(
            culture='en', title='Mont Blanc from the air', description='...',
            gear='paraglider')

        self.locale_fr = RouteLocale(
            culture='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider')

        self.route.locales.append(self.locale_en)
        self.route.locales.append(self.locale_fr)

        self.route.geometry = DocumentGeometry(
            geom='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)')

        self.session.add(self.route)
        self.session.flush()

        DocumentRest(None)._create_new_version(self.route)

        self.route2 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1')
        self.session.add(self.route2)
        self.route3 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1')
        self.session.add(self.route3)
        self.route4 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1')
        self.route4.locales.append(RouteLocale(
            culture='en', title='Mont Blanc from the air', description='...',
            gear='paraglider'))
        self.route4.locales.append(RouteLocale(
            culture='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider'))
        self.session.add(self.route4)
        self.session.flush()
