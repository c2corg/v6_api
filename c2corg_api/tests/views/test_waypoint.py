import datetime
import json

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mappings.route_mapping import SearchRoute
from c2corg_api.tests.search import reset_search_index
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, Point

from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale,
    WAYPOINT_TYPE)
from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentGeometry, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestWaypointRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/waypoints", WAYPOINT_TYPE, Waypoint, ArchiveWaypoint,
            ArchiveWaypointLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertIn('waypoint_type', doc)
        self.assertIn('elevation', doc)
        self.assertIn('geometry', doc)
        self.assertNotIn('routes_quantity', doc)
        locale = doc['locales'][0]
        self.assertIn('title', locale)
        self.assertIn('summary', locale)
        self.assertNotIn('description', locale)
        self.assertIn('areas', doc)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_paginated(self):
        self.app.get("/waypoints?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.waypoint4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.waypoint4.document_id, self.waypoint3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.waypoint3.document_id, self.waypoint2.document_id], 4)

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'wtyp': 'climbing_outdoor,summit'}),
            [self.waypoint4.document_id, self.waypoint3.document_id,
             self.waypoint2.document_id, self.waypoint.document_id], 4)

        body = self.get_collection_search(
            {'wtyp': 'climbing_outdoor,summit', 'limit': 2})
        self.assertEqual(body.get('total'), 4)
        self.assertEqual(len(body.get('documents')), 2)

        body = self.get_collection_search({'a': str(self.area2.document_id)})
        self.assertEqual(body.get('total'), 1)

        body = self.get_collection_search({'walt': '2000'})
        self.assertEqual(body.get('total'), 1)

    def test_get_collection_search_bbox(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search(
                {'bbox': '659000,5694000,660000,5695000'}),
            [self.waypoint4.document_id], 1)

    def test_get(self):
        body = self.get(self.waypoint)
        self._assert_geometry(body)
        self.assertIn('waypoint_type', body)
        self.assertNotIn('routes_quantity', body)

        self.assertIn('associations', body)
        associations = body.get('associations')

        linked_waypoints = associations.get('waypoints')
        self.assertEqual(1, len(linked_waypoints))
        self.assertEqual(
            self.waypoint4.document_id, linked_waypoints[0].get('document_id'))
        self.assertIn('type', linked_waypoints[0])

        linked_routes = associations.get('routes')
        self.assertEqual(1, len(linked_routes))
        linked_route = linked_routes[0]
        self.assertIn('type', linked_route)
        self.assertEqual(
            self.route1.document_id, linked_route.get('document_id'))
        self.assertEqual(
            linked_route.get('locales')[0].get('title_prefix'), 'Mont Blanc :')

        self.assertIn('maps', body)
        self.assertEqual(1, len(body.get('maps')))
        topo_map = body.get('maps')[0]
        self.assertIn('type', topo_map)
        self.assertEqual(topo_map.get('code'), '3232ET')
        self.assertEqual(topo_map.get('locales')[0].get('title'), 'Belley')

        self.assertIn('areas', body)
        area = body.get('areas')[0]
        self.assertIn('type', area)
        self.assertEqual(area.get('area_type'), 'range')
        self.assertEqual(area.get('locales')[0].get('title'), 'France')

        recent_outings = associations.get('recent_outings')
        self.assertEqual(1, recent_outings['total'])
        self.assertEqual(1, len(recent_outings['outings']))
        self.assertEqual(
            self.outing1.document_id,
            recent_outings['outings'][0].get('document_id'))
        self.assertIn('type', recent_outings['outings'][0])

    def test_get_with_empty_arrays(self):
        """Test-case for https://github.com/c2corg/v6_api/issues/231
        """
        self.assertEqual(self.waypoint2.rock_types, [])
        response = self.app.get(self._prefix + '/' +
                                str(self.waypoint2.document_id),
                                status=200)
        body = response.json
        self.assertIn('rock_types', body)
        self.assertEqual(body['rock_types'], [])

    def test_get_no_associations(self):
        response = self.app.get(self._prefix + '/' +
                                str(self.waypoint.document_id) + '?a=0',
                                status=200)
        body = response.json

        self.assertNotIn('associations', body)
        self.assertIn('maps', body)
        self.assertNotIn('areas', body)

    def test_get_version(self):
        self.get_version(self.waypoint, self.waypoint_version)

    def test_get_lang(self):
        body = self.get_lang(self.waypoint)

        self.assertEqual(
            'Mont Granier',
            body.get('locales')[0].get('title'))

    def test_get_new_lang(self):
        self.get_new_lang(self.waypoint)

    def test_get_404(self):
        self.get_404()

    def test_get_redirected_wp(self):
        response = self.app.get(self._prefix + '/' +
                                str(self.waypoint5.document_id),
                                status=200)
        body = response.json

        self.assertIn('redirects_to', body)
        self.assertEqual(body['redirects_to'], self.waypoint.document_id)
        self.assertEqual(body['available_langs'], ['en', 'fr'])

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceMissing(errors[0], 'waypoint_type')

    def test_post_missing_title(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [
                {'lang': 'en'}
            ]
        }
        body = self.post_missing_title(body)
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[1], 'locales')

    def test_post_missing_geometry(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        self.post_missing_geometry(body)

    def test_post_missing_geom(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {},
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        self.post_missing_geom(body)

    def test_post_missing_locales(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': []
        }
        self.post_missing_locales(body)

    def test_post_same_locale_twice(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'},
                {'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}
            ]
        }
        self.post_same_locale_twice(body)

    def test_post_missing_elevation(self):
        body = {
            'waypoint_type': 'summit',
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        self.post_missing_field(body, 'elevation')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'protected': True,
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_invalid_waypoint_type(self):
        body_post = {
            'geometry': {
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail':
                    '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'waypoint_type': 'swimming-pool',
            'elevation': 3779,
            'locales': [
                {'lang': 'en', 'title': 'Mont Pourri'}
            ]
        }
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].get('description').startswith(
            '"swimming-pool" is not one of'))
        self.assertEqual(errors[0].get('name'), 'waypoint_type')

    def test_post_success(self):
        body = {
            'document_id': 1234,
            'version': 2345,
            'geometry': {
                'document_id': 5678, 'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
                'geom_detail':
                    '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {'id': 3456, 'version': 4567,
                 'lang': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body, 'geom')

        # test that document_id and version was reset
        self.assertNotEqual(body.get('document_id'), 1234)
        self.assertEqual(body.get('version'), 1)
        self.assertNotEqual(doc.locales[0].id, 3456)
        self.assertEqual(body.get('locales')[0].get('version'), 1)
        self.assertEqual(doc.geometry.document_id, doc.document_id)
        self.assertEqual(doc.geometry.version, 1)
        version = doc.versions[0]

        archive_waypoint = version.document_archive
        self.assertEqual(archive_waypoint.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint.elevation, 3779)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Mont Pourri')
        self.assertEqual(archive_locale.access, 'y')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertEqual(
            archive_geometry.document_id, doc.geometry.document_id)
        self.assertIsNotNone(archive_geometry.geom)
        self.assertIsNotNone(archive_geometry.geom_detail)

        # check that a link for intersecting areas is created
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.document_id == doc.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].area_id, self.area1.document_id)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': '...', 'access': 'n'}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': -9999,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': '...', 'access': 'n'}
                ]
            }
        }
        self.put_wrong_version(body, self.waypoint.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': '...', 'access': 'n',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.waypoint.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'access': 'n',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.waypoint.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.waypoint.document_id)

    def test_put_missing_elevation(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit'
            }
        }
        self.put_missing_field(body, self.waypoint, 'elevation')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 1234,
                'orientations': None,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier!',
                     'description': 'A.', 'access': 'n',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.waypoint.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [635957, 5723605]}'  # noqa
                }
            }
        }
        (body, waypoint) = self.put_success_all(body, self.waypoint)

        self.assertEquals(waypoint.elevation, 1234)
        locale_en = waypoint.get_locale('en')
        self.assertEquals(locale_en.description, 'A.')
        self.assertEquals(locale_en.access, 'n')

        # version with lang 'en'
        versions = waypoint.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier!')
        self.assertEqual(archive_locale.access, 'n')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.waypoint_type, 'summit')
        self.assertEqual(archive_document_en.elevation, 1234)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with lang 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.access, 'ouai')

        # check that the title_prefix of an associated route (that the wp
        # it the main wp of) was updated
        route = self.session.query(Route).get(self.route1.document_id)
        route_locale_en = route.get_locale('en')
        self.assertEqual(route_locale_en.title_prefix, 'Mont Granier!')

        # check that the route was updated in the search index
        search_doc = SearchRoute.get(
            id=route.document_id,
            index=elasticsearch_config['index'])
        self.assertEqual(
            search_doc['title_en'], 'Mont Granier! : Mont Blanc from the air')

        # check that the links for intersecting areas are updated
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.document_id == self.waypoint.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].area_id, self.area1.document_id)

    def test_put_success_figures_and_lang_only(self):
        body_put = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'access': 'n',
                     'version': self.locale_en.version}
                ],
                'geometry': None
            }
        }
        (body, waypoint) = self.put_success_all(body_put, self.waypoint)
        document_id = body.get('document_id')
        self.assertEquals(body.get('version'), 2)

        self.session.expire_all()
        # check that a new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 2)

        # check that a new archive_document_locale was created
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 3)

        # check that a new archive_document_geometry was created
        archive_geometry_count = \
            self.session.query(ArchiveDocumentGeometry). \
            filter(document_id == ArchiveDocumentGeometry.document_id). \
            count()
        self.assertEqual(archive_geometry_count, 1)

        self.assertEquals(waypoint.elevation, 1234)
        locale_en = waypoint.get_locale('en')
        self.assertEquals(locale_en.description, 'A.')
        self.assertEquals(locale_en.access, 'n')

        # version with lang 'en'
        versions = waypoint.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.access, 'n')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.waypoint_type, 'summit')
        self.assertEqual(archive_document_en.elevation, 1234)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 1)

        # version with lang 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.access, 'ouai')

        # check that the links to intersecting areas are not updated,
        # because the geometry did not change
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.document_id == self.waypoint.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].area_id, self.area2.document_id)

    def test_put_success_figures_only(self):
        """Test updating a document with only changes to the figures.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': []
            }
        }
        (body, waypoint) = self.put_success_figures_only(body, self.waypoint)

        self.assertEquals(waypoint.elevation, 1234)

    def test_put_boolean_default_values(self):
        """Test-case for https://github.com/c2corg/v6_api/issues/229
        """
        self.assertIsNone(self.waypoint.blanket_unstaffed)
        self.assertIsNone(self.waypoint.matress_unstaffed)
        self.assertIsNone(self.waypoint.gas_unstaffed)
        self.assertIsNone(self.waypoint.heating_unstaffed)

        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 1234,
                'blanket_unstaffed': True,
                'matress_unstaffed': False,
                'gas_unstaffed': None,
                'locales': []
            }
        }
        (_, waypoint) = self.put_success_figures_only(body, self.waypoint)

        self.assertEquals(waypoint.blanket_unstaffed, True)
        self.assertEquals(waypoint.matress_unstaffed, False)
        self.assertIsNone(waypoint.gas_unstaffed)
        self.assertIsNone(waypoint.heating_unstaffed)

    def test_put_success_lang_only(self):
        """Test updating a document with only changes to a locale.
        """
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Granier',
                     'description': '...', 'access': 'no',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, waypoint) = self.put_success_lang_only(body, self.waypoint)

        self.assertEquals(waypoint.get_locale('en').access, 'no')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'id': 1234, 'version': 2345,
                     'lang': 'es', 'title': 'Mont Granier',
                     'description': '...', 'access': 'si'}
                ]
            }
        }
        (body, waypoint) = self.put_success_new_lang(body, self.waypoint)

        self.assertEquals(waypoint.get_locale('es').access, 'si')
        self.assertNotEqual(waypoint.get_locale('es').version, 2345)
        self.assertNotEqual(waypoint.get_locale('es').id, 1234)

    def test_put_add_geometry(self):
        """Tests adding a geometry to a waypoint without geometry.
        """
        # first create a waypoint with no geometry
        waypoint = Waypoint(
            waypoint_type='summit', elevation=3779)

        locale_en = WaypointLocale(
            lang='en', title='Mont Pourri', access='y')
        waypoint.locales.append(locale_en)

        self.session.add(waypoint)
        self.session.flush()
        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(waypoint, user_id)

        # then add a geometry to the waypoint
        body_put = {
            'message': 'Adding geom',
            'document': {
                'document_id': waypoint.document_id,
                'version': waypoint.version,
                'quality': quality_types[1],
                'geometry': {
                    'geom':
                        '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': []
            }
        }
        response = self.app_put_json(
            self._prefix + '/' + str(waypoint.document_id), body_put,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(waypoint.document_id), body_put,
            headers=headers, status=200)

        response = self.app.get(
            self._prefix + '/' + str(waypoint.document_id), status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        document_id = body.get('document_id')
        self.assertEquals(
            body.get('version'), body_put.get('document').get('version'))

        # check that no new archive_document was created
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)

        # check that a new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 1)

        # check that no new archive_document_locale was created
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 1)

        # check that a new archive_document_geometry was created
        archive_locale_count = \
            self.session.query(ArchiveDocumentGeometry). \
            filter(document_id == ArchiveDocumentGeometry.document_id). \
            count()
        self.assertEqual(archive_locale_count, 1)

        # check that new versions were created
        versions = document.versions
        self.assertEqual(len(versions), 2)

        # version with lang 'en'
        version_en = versions[1]

        self.assertEqual(version_en.lang, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Adding geom')
        self.assertIsNotNone(meta_data_en.written_at)

    def test_put_merged_wp(self):
        """Tests updating a waypoint with `redirected_to` set.
        """
        body_put = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint5.document_id,
                'version': self.waypoint5.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': []
            }
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_put_json(
            self._prefix + '/' + str(self.waypoint5.document_id), body_put,
            headers=headers, status=400)

        errors = response.json.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'can not update merged document')
        self.assertEqual(errors[0].get('name'), 'Bad Request')

    def test_put_protected_no_permission(self):
        """Tests updating a protected waypoint as non-moderator.
        """
        body_put = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint4.document_id,
                'version': self.waypoint4.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': []
            }
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_put_json(
            self._prefix + '/' + str(self.waypoint4.document_id), body_put,
            headers=headers, status=403)

        errors = response.json.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'),
            'No permission to change a protected document')
        self.assertEqual(errors[0].get('name'), 'Forbidden')

    def test_put_protected_as_moderator(self):
        """Tests updating a protected waypoint as moderator.
        """
        body_put = {
            'message': 'Updating',
            'document': {
                'document_id': self.waypoint4.document_id,
                'version': self.waypoint4.version,
                'quality': quality_types[1],
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': []
            }
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.waypoint4.document_id), body_put,
            headers=headers, status=200)

    def _assert_geometry(self, body, field='geom'):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get(field))

        geom = geometry.get(field)
        point = shape(json.loads(geom))
        self.assertIsInstance(point, Point)
        self.assertAlmostEqual(point.x, 635956)
        self.assertAlmostEqual(point.y, 5723604)

    def test_history(self):
        id = self.waypoint.document_id
        langs = ['fr', 'en']
        for lang in langs:
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

    def _add_test_data(self):
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)

        self.locale_en = WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep')

        self.locale_fr = WaypointLocale(
            lang='fr', title='Mont Granier', description='...',
            access='ouai')

        self.waypoint.locales.append(self.locale_en)
        self.waypoint.locales.append(self.locale_fr)

        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.waypoint)
        self.session.flush()
        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.waypoint, user_id)
        self.waypoint_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.waypoint.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor', elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.session.add(self.waypoint2)
        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=3,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.session.add(self.waypoint3)
        self.waypoint4 = Waypoint(
            waypoint_type='summit', elevation=4,
            protected=True,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(659775 5694854)'))
        self.waypoint4.locales.append(WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep'))
        self.waypoint4.locales.append(WaypointLocale(
            lang='fr', title='Mont Granier', description='...',
            access='ouai'))
        self.session.add(self.waypoint4)
        self.waypoint5 = Waypoint(
            waypoint_type='summit', elevation=3,
            redirects_to=self.waypoint.document_id,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint5.locales.append(WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep'))
        self.session.add(self.waypoint5)
        self.session.flush()
        DocumentRest.create_new_version(
            self.waypoint4, self.global_userids['contributor'])
        DocumentRest.create_new_version(
            self.waypoint5, self.global_userids['contributor'])

        # add some associations
        self.route1 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            main_waypoint_id=self.waypoint.document_id
        )
        self.route1.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            title_prefix='Mont Blanc :', gear='paraglider'))
        self.session.add(self.route1)
        self.session.flush()
        self.route2 = Route(
            redirects_to=self.route1.document_id,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            main_waypoint_id=self.waypoint.document_id
        )
        self.session.add(self.route2)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.waypoint4.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.waypoint5.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route1.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route2.document_id))

        self.outing1 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny')
            ]
        )
        self.session.add(self.outing1)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route1.document_id,
            child_document_id=self.outing1.document_id))

        self.outing2 = Outing(
            redirects_to=self.outing1.document_id,
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny')
            ]
        )
        self.session.add(self.outing2)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route1.document_id,
            child_document_id=self.outing2.document_id))

        # add a map
        topo_map = TopoMap(
            code='3232ET', editor='IGN', scale='25000',
            locales=[
                DocumentLocale(lang='fr', title='Belley')
            ],
            geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))')  # noqa
        )
        self.session.add(topo_map)
        self.session.flush()
        self.session.add(TopoMap(
            redirects_to=topo_map.document_id,
            code='3232ET', editor='IGN', scale='25000',
            locales=[
                DocumentLocale(lang='fr', title='Belley')
            ],
            geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))')  # noqa
        ))

        # add areas
        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            )
        )
        self.area2 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='France')
            ]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.add(AreaAssociation(
            document=self.waypoint, area=self.area2))
        self.session.flush()
