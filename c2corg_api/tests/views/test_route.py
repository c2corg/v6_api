import json

from c2corg_api.models.association import Association
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.views.route import update_title_prefix
from shapely.geometry import shape, LineString

from c2corg_api.models.route import (
    Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale)
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestRouteRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/routes", Route, ArchiveRoute, ArchiveRouteLocale)
        BaseDocumentTestRest.setUp(self)
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

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get(self):
        body = self.get(self.route)
        self.assertEqual(
            body.get('activities'), self.route.activities)
        self._assert_geometry(body)
        self.assertNotIn('climbing_outdoor_types', body)
        self.assertIn('elevation_min', body)

        self.assertIn('main_waypoint_id', body)
        self.assertIn('associations', body)
        associations = body.get('associations')

        linked_waypoints = associations.get('waypoints')
        self.assertEqual(1, len(linked_waypoints))
        self.assertEqual(
            self.waypoint.document_id, linked_waypoints[0].get('document_id'))

        linked_routes = associations.get('routes')
        self.assertEqual(1, len(linked_routes))
        self.assertEqual(
            self.route4.document_id, linked_routes[0].get('document_id'))

    def test_get_version(self):
        self.get_version(self.route, self.route_version)

    def test_get_lang(self):
        self.get_lang(self.route)

    def test_get_new_lang(self):
        self.get_new_lang(self.route)

    def test_get_404(self):
        self.get_404()

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceMissing(errors[0], 'activities')

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
        self.assertCorniceRequired(errors[1], 'locales')

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
            'main_waypoint_id': self.waypoint.document_id,
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

        self.assertEqual(doc.main_waypoint_id, self.waypoint.document_id)
        self.assertEqual(
            body.get('main_waypoint_id'), self.waypoint.document_id)
        self.assertEqual(
            archive_route.main_waypoint_id, self.waypoint.document_id)

        self.assertEqual(
            self.waypoint.locales[0].title, doc.locales[0].title_prefix)

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
                     'version': self.locale_en.version,
                     'title_prefix': 'Should be ignored'}
                ]
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)

        self.assertEquals(route.elevation_max, 1600)

    def test_put_success_main_wp_changed(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'main_waypoint_id': self.waypoint.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
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

        self.assertEqual(route.main_waypoint_id, self.waypoint.document_id)
        locale_en = route.get_locale('en')
        self.assertEqual(
            locale_en.title_prefix, self.waypoint.get_locale('en').title)

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

    def test_history(self):
        id = self.route.document_id
        cultures = ['fr', 'en']
        for lang in cultures:
            body = self.app.get('/document/%d/history/%s' % (id, lang))
            username = 'contributor'
            user_id = self.global_userids[username]

            title = body.json['title']
            versions = body.json['versions']
            self.assertEqual(len(versions), 1)
            self.assertEqual(getattr(self, 'locale_' + lang).title, title)
            for r in versions:
                self.assertEqual(r['username'], username)
                self.assertEqual(r['user_id'], user_id)
                self.assertIn('written_at', r)
                self.assertIn('version_id', r)

    def test_history_no_lang(self):
        id = self.route.document_id
        self.app.get('/document/%d/history/es' % id, status=404)

    def test_history_no_doc(self):
        self.app.get('/document/99999/history/es', status=404)

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

    def test_update_prefix_title(self):
        self.route.locales.append(RouteLocale(
            culture='es', title='Mont Blanc del cielo', description='...',
            gear='paraglider'))
        self.route.main_waypoint_id = self.waypoint.document_id
        self.session.flush()
        self.session.refresh(self.route)
        update_title_prefix(self.route, create=False)

        route = self.session.query(Route).get(self.route.document_id)
        locale_en = route.get_locale('en')
        self.assertEqual(locale_en.version, 1)
        self.assertEqual(
            locale_en.title_prefix, self.waypoint.get_locale('en').title)
        locale_fr = route.get_locale('fr')
        self.assertEqual(locale_fr.version, 1)
        self.assertEqual(
            locale_fr.title_prefix, self.waypoint.get_locale('fr').title)
        locale_es = route.get_locale('es')
        self.assertEqual(locale_es.version, 1)
        self.assertEqual(
            locale_es.title_prefix, self.waypoint.get_locale('fr').title)

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

        user_id = self.global_userids['contributor']
        DocumentRest(None)._create_new_version(self.route, user_id)
        self.route_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.route.document_id). \
            filter(DocumentVersion.culture == 'en').first()

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

        # add some associations
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=4,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint.locales.append(WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            access='yep'))
        self.waypoint.locales.append(WaypointLocale(
            culture='fr', title='Mont Granier', description='...',
            access='ouai'))
        self.session.add(self.waypoint)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route.document_id,
            child_document_id=self.route4.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route.document_id))
        self.session.flush()
