import json

from c2corg_api.models.route import Route
from c2corg_api.models.topo_map import ArchiveTopoMap, TopoMap, MAP_TYPE
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests.search import reset_search_index
from c2corg_api.models.common.attributes import quality_types
from shapely.geometry import shape, Polygon

from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestTopoMapRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/maps", MAP_TYPE, TopoMap, ArchiveTopoMap, ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertNotIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.app.get("/maps?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.map4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.map4.document_id, self.map3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.map3.document_id, self.map2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.map4.document_id, self.map1.document_id], 2)

    def test_get(self):
        body = self.get(self.map1)
        self._assert_geometry(body)
        self.assertNotIn('maps', body)

    def test_get_cooked(self):
        self.get_cooked(self.map1)

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.map1)

    def test_get_lang(self):
        self.get_lang(self.map1)

    def test_get_new_lang(self):
        self.get_new_lang(self.map1)

    def test_get_404(self):
        self.get_404()

    def test_get_caching(self):
        self.get_caching(self.map1)

    def test_get_info(self):
        body, locale = self.get_info(self.map1, 'en')
        self.assertEqual(locale.get('lang'), 'en')

    def test_post_not_moderator(self):
        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, {}, headers=headers,
            expect_errors=True, status=403)

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales')
        self.assertCorniceRequired(errors[1], 'geometry')

    def test_post_missing_title(self):
        body_post = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [
                {'lang': 'en'}
            ]
        }
        self.post_missing_title(body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'protected': True,
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [
                {'lang': 'en', 'title': 'Lac d\'Annecy'}
            ]
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [
                {'lang': 'en', 'title': 'Lac d\'Annecy'}
            ]
        }
        body, doc = self.post_success(body, user='moderator')
        self.assertIsNotNone(body['geometry'].get('geom_detail'))

        version = doc.versions[0]

        archive_map = version.document_archive
        self.assertEqual(archive_map.editor, 'IGN')
        self.assertEqual(archive_map.scale, '25000')
        self.assertEqual(archive_map.code, '3432OT')

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom_detail)
        self.assertIsNotNone(archive_geometry.geom_detail)

        # check that a link for intersecting documents is created
        links = self.session.query(TopoMapAssociation). \
            filter(
                TopoMapAssociation.topo_map_id == doc.document_id). \
            order_by(TopoMapAssociation.document_id). \
            all()
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].document_id, self.waypoint1.document_id)
        self.check_cache_version(self.waypoint1.document_id, 2)
        self.assertEqual(links[1].document_id, self.route.document_id)
        self.check_cache_version(self.route.document_id, 2)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': -9999,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.map1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.map1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.map1.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.map1.document_id, user='moderator')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': quality_types[1],
                'editor': 'IGN',
                'scale': '25000',
                'code': '3433OT',
                'geometry': {
                    'version': self.map1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
                },
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, map1) = self.put_success_all(body, self.map1, user='moderator')

        self.assertEqual(map1.code, '3433OT')
        locale_en = map1.get_locale('en')
        self.assertEqual(locale_en.title, 'New title')

        # version with lang 'en'
        versions = map1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'New title')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.scale, '25000')
        self.assertEqual(archive_document_en.code, '3433OT')

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        # check that the links to intersecting documents are updated
        links = self.session.query(TopoMapAssociation). \
            filter(
                TopoMapAssociation.topo_map_id == self.map1.document_id). \
            all()
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].document_id, self.waypoint1.document_id)
        self.check_cache_version(self.waypoint1.document_id, 2)
        self.assertEqual(links[1].document_id, self.route.document_id)
        self.check_cache_version(self.route.document_id, 2)
        # waypoint 2 is no longer associated, the cache key was incremented
        self.check_cache_version(self.waypoint2.document_id, 2)

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': quality_types[1],
                'editor': 'IGN',
                'scale': '25000',
                'code': '3433OT',
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, map1) = self.put_success_figures_only(
            body, self.map1, user='moderator')

        self.assertEqual(map1.code, '3433OT')

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': quality_types[1],
                'editor': 'IGN',
                'scale': '25000',
                'code': '3431OT',
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, map1) = self.put_success_lang_only(
            body, self.map1, user='moderator')

        self.assertEqual(
            map1.get_locale('en').title, 'New title')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': quality_types[1],
                'editor': 'IGN',
                'scale': '25000',
                'code': '3431OT',
                'locales': [
                    {'lang': 'es', 'title': 'Lac d\'Annecy'}
                ]
            }
        }
        (body, map1) = self.put_success_new_lang(
            body, self.map1, user='moderator')

        self.assertEqual(map1.get_locale('es').title, 'Lac d\'Annecy')

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom_detail'))

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        self.assertIsInstance(polygon, Polygon)

    def _add_test_data(self):
        self.map1 = TopoMap(editor='IGN', scale='25000', code='3431OT')

        self.locale_en = DocumentLocale(lang='en', title='Lac d\'Annecy')
        self.locale_fr = DocumentLocale(lang='fr', title='Lac d\'Annecy')

        self.map1.locales.append(self.locale_en)
        self.map1.locales.append(self.locale_fr)

        self.map1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774 5706934,611774 5744215,'
                        '642834 5744215,642834 5706934,611774 5706934))')

        self.session.add(self.map1)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.map1, user_id)

        self.map2 = TopoMap(
            editor='IGN', scale='25000', code='3432OT')
        self.session.add(self.map2)
        self.map3 = TopoMap(
            editor='IGN', scale='25000', code='3433OT')
        self.session.add(self.map3)
        self.map4 = TopoMap(
            editor='IGN', scale='25000', code='3434OT')
        self.map4.locales.append(DocumentLocale(
            lang='en', title='Lac d\'Annecy'))
        self.map4.locales.append(DocumentLocale(
            lang='fr', title='Lac d\'Annecy'))
        self.session.add(self.map4)
        self.session.flush()

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)')
        )
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(693666.031687976 5741108.7574713)')
        )
        route_geom = 'SRID=3857;LINESTRING(668518 5728802, 668528 5728812)'
        self.route = Route(
            activities=['skitouring'],
            geometry=DocumentGeometry(geom_detail=route_geom))

        self.session.add_all([self.waypoint1, self.waypoint2, self.route])
        self.session.add(TopoMapAssociation(
            document=self.waypoint2, topo_map=self.map1))
        self.session.flush()
