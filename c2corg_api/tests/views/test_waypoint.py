import json

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mapping import SearchDocument
from shapely.geometry import shape, Point

from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)
from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentGeometry, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestWaypointRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/waypoints", Waypoint, ArchiveWaypoint, ArchiveWaypointLocale)
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

        self.assertResultsEqual(
            self.get_collection(
                {'after': self.waypoint3.document_id, 'limit': 1}),
            [self.waypoint2.document_id], -1)

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

        linked_routes = associations.get('routes')
        self.assertEqual(1, len(linked_routes))
        self.assertEqual(
            self.route.document_id, linked_routes[0].get('document_id'))

        self.assertIn('maps', body)
        topo_map = body.get('maps')[0]
        self.assertEqual(topo_map.get('code'), '3232ET')
        self.assertEqual(topo_map.get('locales')[0].get('title'), 'Belley')

        self.assertIn('areas', body)
        area = body.get('areas')[0]
        self.assertEqual(area.get('area_type'), 'range')
        self.assertEqual(area.get('locales')[0].get('title'), 'France')

    def test_get_version(self):
        self.get_version(self.waypoint, self.waypoint_version)

    def test_get_lang(self):
        self.get_lang(self.waypoint)

    def test_get_new_lang(self):
        self.get_new_lang(self.waypoint)

    def test_get_404(self):
        self.get_404()

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
                {'culture': 'en'}
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
                {'culture': 'en', 'title': 'Mont Pourri',
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
                {'culture': 'en', 'title': 'Mont Pourri',
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
                {'culture': 'en', 'title': 'Mont Pourri', 'access': 'y'},
                {'culture': 'en', 'title': 'Mont Pourri', 'access': 'y'}
            ]
        }
        self.post_same_locale_twice(body)

    def test_post_missing_elevation(self):
        body = {
            'waypoint_type': 'summit',
            'geometry': {'geom': '{"type": "Point", "coordinates": [1, 1]}'},
            'locales': [
                {'culture': 'en', 'title': 'Mont Pourri',
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
                {'culture': 'en', 'title': 'Mont Pourri',
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
                {'culture': 'en', 'title': 'Mont Pourri'}
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
                 'culture': 'en', 'title': 'Mont Pourri',
                 'access': 'y'}
            ]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body, 'geom')
        self._assert_geometry(body, 'geom_detail')

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
        self.assertEqual(archive_locale.culture, 'en')
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
                    {'culture': 'en', 'title': 'Mont Granier',
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
                    {'culture': 'en', 'title': 'Mont Granier',
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
                    {'culture': 'en', 'title': 'Mont Granier',
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
                    {'culture': 'en', 'title': 'Mont Granier',
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
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier!',
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

        # version with culture 'en'
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

        # version with culture 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.access, 'ouai')

        # check that the title_prefix of an associated route (that the wp
        # it the main wp of) was updated
        route = self.session.query(Route).get(self.route.document_id)
        route_locale_en = route.get_locale('en')
        self.assertEqual(route_locale_en.title_prefix, 'Mont Granier!')

        # check that the route was updated in the search index
        search_doc = SearchDocument.get(
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
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'access': 'n',
                     'version': self.locale_en.version}
                ]
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

        # version with culture 'en'
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

        # version with culture 'fr'
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
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': []
            }
        }
        (body, waypoint) = self.put_success_figures_only(body, self.waypoint)

        self.assertEquals(waypoint.elevation, 1234)

    def test_put_success_lang_only(self):
        """Test updating a document with only changes to a locale.
        """
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
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
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'id': 1234, 'version': 2345,
                     'culture': 'es', 'title': 'Mont Granier',
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
            culture='en', title='Mont Pourri', access='y')
        waypoint.locales.append(locale_en)

        self.session.add(waypoint)
        self.session.flush()
        user_id = self.global_userids['contributor']
        DocumentRest(None)._create_new_version(waypoint, user_id)

        # then add a geometry to the waypoint
        body_put = {
            'message': 'Adding geom',
            'document': {
                'document_id': waypoint.document_id,
                'version': waypoint.version,
                'geometry': {
                    'geom':
                        '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'waypoint_type': 'summit',
                'elevation': 3779,
                'locales': []
            }
        }
        response = self.app.put_json(
            self._prefix + '/' + str(waypoint.document_id), body_put,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(waypoint.document_id), body_put,
            headers=headers, status=200)

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

        # version with culture 'en'
        version_en = versions[1]

        self.assertEqual(version_en.culture, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Adding geom')
        self.assertIsNotNone(meta_data_en.written_at)

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

    def _add_test_data(self):
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)

        self.locale_en = WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            access='yep')

        self.locale_fr = WaypointLocale(
            culture='fr', title='Mont Granier', description='...',
            access='ouai')

        self.waypoint.locales.append(self.locale_en)
        self.waypoint.locales.append(self.locale_fr)

        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.waypoint)
        self.session.flush()
        user_id = self.global_userids['contributor']
        DocumentRest(None)._create_new_version(self.waypoint, user_id)
        self.waypoint_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.waypoint.document_id). \
            filter(DocumentVersion.culture == 'en').first()

        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=2,
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
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint4.locales.append(WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            access='yep'))
        self.waypoint4.locales.append(WaypointLocale(
            culture='fr', title='Mont Granier', description='...',
            access='ouai'))
        self.session.add(self.waypoint4)

        # add some associations
        self.route = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            main_waypoint_id=self.waypoint.document_id
        )
        self.route.locales.append(RouteLocale(
            culture='en', title='Mont Blanc from the air', description='...',
            gear='paraglider'))
        self.session.add(self.route)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.waypoint4.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route.document_id))

        # add a map
        self.session.add(TopoMap(
            code='3232ET', editor='ign', scale='25000',
            locales=[
                DocumentLocale(culture='fr', title='Belley')
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))')  # noqa
        ))

        # add areas
        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa
            )
        )
        self.area2 = Area(
            area_type='range',
            locales=[
                DocumentLocale(culture='fr', title='France')
            ]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.add(AreaAssociation(
            document=self.waypoint, area=self.area2))
        self.session.flush()
