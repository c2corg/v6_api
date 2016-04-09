import json

from c2corg_api.models.area import Area, ArchiveArea, AREA_TYPE
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, Polygon

from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentLocale, DocumentLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest


class TestAreaRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/areas", AREA_TYPE, Area, ArchiveArea, ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertNotIn('areas', doc)
        self.assertNotIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.app.get("/areas?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.area4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.area4.document_id, self.area3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.area3.document_id, self.area2.document_id], 4)

        self.assertResultsEqual(
            self.get_collection(
                {'after': self.area3.document_id, 'limit': 1}),
            [self.area2.document_id], -1)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get(self):
        body = self.get(self.area1)
        self._assert_geometry(body)
        self.assertNotIn('maps', body)

    def test_get_lang(self):
        self.get_lang(self.area1)

    def test_get_new_lang(self):
        self.get_new_lang(self.area1)

    def test_get_404(self):
        self.get_404()

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 3)
        self.assertCorniceRequired(errors[0], 'locales')
        self.assertCorniceRequired(errors[1], 'geometry')
        self.assertCorniceRequired(errors[2], 'area_type')

    def test_post_missing_title(self):
        body_post = {
            'area_type': 'range',
            'geometry': {
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}'  # noqa
            },
            'locales': [
                {'lang': 'en'}
            ]
        }
        body = self.post_missing_title(body_post, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[0], 'locales.0.title')
        self.assertCorniceRequired(errors[1], 'locales')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'area_type': 'range',
            'protected': True,
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail': '{"type": "Point", "coordinates": [635956, 5723604]}'  # noqa
            },
            'locales': [
                {'lang': 'en', 'title': 'Chartreuse'}
            ]
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'area_type': 'range',
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}'  # noqa
            },
            'locales': [
                {'lang': 'en', 'title': 'Chartreuse'}
            ]
        }
        body, doc = self.post_success(body, user='moderator')
        self._assert_geometry(body)

        version = doc.versions[0]

        archive_map = version.document_archive
        self.assertEqual(archive_map.area_type, 'range')

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Chartreuse')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom_detail)

        # check that a link for intersecting documents is created
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.area_id == doc.document_id). \
            all()
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].document_id, self.waypoint1.document_id)
        self.assertEqual(links[1].document_id, self.route.document_id)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {'lang': 'en', 'title': 'Chartreuse',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': -9999,
                'area_type': 'range',
                'locales': [
                    {'lang': 'en', 'title': 'Chartreuse',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.area1.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {'lang': 'en', 'title': 'Chartreuse',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.area1.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'locales': [
                    {'lang': 'en', 'title': 'Chartreuse',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.area1.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.area1.document_id)

    def test_put_update_geometry_fail(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'geometry': {
                    'version': self.area1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
                },
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(self.area1.document_id), body,
            headers=headers, status=400)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Bad Request')
        self.assertEqual(
            body['errors'][0]['description'],
            'No permission to change the geometry')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, map1) = self.put_success_all(body, self.area1)

        self.assertEquals(map1.area_type, 'admin_limits')
        locale_en = map1.get_locale('en')
        self.assertEquals(locale_en.title, 'New title')

        # version with lang 'en'
        versions = map1.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'New title')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.area_type, 'admin_limits')

        # geometry has not changed because changes to the geometry are not
        # allowed for non-moderators
        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 1)

        # version with lang 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Chartreuse')

    def test_put_success_all_as_moderator(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'quality': quality_types[1],
                'geometry': {
                    'version': self.area1.geometry.version,
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}'  # noqa
                },
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, map1) = self.put_success_all(body, self.area1, user='moderator')

        # version with lang 'en'
        version_en = map1.versions[2]

        # geometry has been changed because the user is a moderator
        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # check that the links to intersecting documents are updated
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.area_id == self.area1.document_id). \
            all()
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].document_id, self.waypoint1.document_id)
        self.assertEqual(links[1].document_id, self.route.document_id)

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'admin_limits',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'en', 'title': 'Chartreuse',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, area) = self.put_success_figures_only(body, self.area1)

        self.assertEquals(area.area_type, 'admin_limits')

        # check that the links to intersecting documents are not updated,
        # because the geometry did not change
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.area_id == self.area1.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].document_id, self.waypoint2.document_id)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, area) = self.put_success_lang_only(body, self.area1)

        self.assertEquals(
            area.get_locale('en').title, 'New title')

        # check that the links to intersecting documents are not updated,
        # because the geometry did not change
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.area_id == self.area1.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].document_id, self.waypoint2.document_id)

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.area1.document_id,
                'version': self.area1.version,
                'area_type': 'range',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'es', 'title': 'Chartreuse'}
                ]
            }
        }
        (body, area) = self.put_success_new_lang(body, self.area1)

        self.assertEquals(area.get_locale('es').title, 'Chartreuse')

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom_detail'))

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        self.assertIsInstance(polygon, Polygon)

    def _add_test_data(self):
        self.area1 = Area(area_type='range')

        self.locale_en = DocumentLocale(lang='en', title='Chartreuse')
        self.locale_fr = DocumentLocale(lang='fr', title='Chartreuse')

        self.area1.locales.append(self.locale_en)
        self.area1.locales.append(self.locale_fr)

        self.area1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
        )

        self.session.add(self.area1)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.area1, user_id)

        self.area2 = Area(area_type='range')
        self.session.add(self.area2)
        self.area3 = Area(area_type='range')
        self.session.add(self.area3)
        self.area4 = Area(area_type='admin_limits')
        self.area4.locales.append(DocumentLocale(
            lang='en', title='Isère'))
        self.area4.locales.append(DocumentLocale(
            lang='fr', title='Isère'))
        self.session.add(self.area4)

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
        self.session.add(AreaAssociation(
            document=self.waypoint2, area=self.area1))
        self.session.flush()
