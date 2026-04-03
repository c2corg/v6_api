import json

from c2corg_api.models.coverage import Coverage, COVERAGE_TYPE

from c2corg_api.models.common.attributes import quality_types
from shapely.geometry import shape, Polygon

from c2corg_api.models.document import (
    DocumentGeometry, ArchiveDocumentLocale, DocumentLocale)

from c2corg_api.tests.views import BaseDocumentTestRest


class TestCoverageRest(BaseDocumentTestRest):
    """Tests for Coverage, which has no archive / wiki-style versioning.

    Many of the base-class helpers (``post_success``, ``put_success_all``,
    etc.) assume archive tables exist and versions are created. Since
    Coverage skips ``create_new_version``, we write custom POST / PUT
    tests instead.
    """

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/coverages", COVERAGE_TYPE, Coverage,
            Coverage, ArchiveDocumentLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        # coverage2 has no geometry set
        self.assertIsNone(doc.get('geometry'))

    def test_get_collection_paginated(self):
        self.app.get("/coverages?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 2)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.coverage2.document_id], 2)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.coverage2.document_id, self.coverage1.document_id], 2)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get(self):
        body = self.get(self.coverage1)
        self._assert_geometry(body)

    def test_get_cooked(self):
        self.get_cooked(self.coverage1)

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.coverage1)

    def test_get_lang(self):
        self.get_lang(self.coverage1)

    def test_get_new_lang(self):
        self.get_new_lang(self.coverage1)

    def test_get_404(self):
        self.get_404()

    def test_get_caching(self):
        self.get_caching(self.coverage1)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertGreaterEqual(len(errors), 1)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'coverage_type': 'fr-se',
            'protected': True,
            'geometry': {
                'geom_detail': self._polygon_geojson()
            },
            'locales': [
                {'lang': 'en', 'title': 'South-East France'}
            ]
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'coverage_type': 'fr-ne',
            'geometry': {
                'geom_detail': self._polygon_geojson()
            },
            'locales': [
                {'lang': 'en', 'title': 'North-East France'}
            ]
        }
        # Coverage has no archive, so skip the standard version validation
        body, doc = self.post_success(body, user='moderator',
                                      skip_validation=True)
        self.assertIsNotNone(body.get('document_id'))
        document_id = body.get('document_id')

        doc = self.session.get(Coverage, document_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.coverage_type, 'fr-ne')
        self.assertEqual(len(doc.locales), 1)
        self.assertEqual(doc.locales[0].title, 'North-East France')
        self.assertIsNotNone(doc.geometry)
        self.assertIsNotNone(doc.geometry.geom_detail)

    def test_post_wrong_geom_type(self):
        body = {
            'coverage_type': 'fr-se',
            'geometry': {
                'geom_detail':
                    '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Wrong geom'}
            ]
        }
        errors = self.post_wrong_geom_type(body)
        self.assertEqual(
            errors[0]['description'],
            "Invalid geometry type. Expected: ['POLYGON']."
            " Got: POINT.")

    # ------------------------------------------------------------------
    # PUT
    # ------------------------------------------------------------------

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': -9999,
                'coverage_type': 'fr-se',
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(
            body, self.coverage1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(
            body, self.coverage1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(
            body, self.coverage1.document_id, user='moderator')

    def test_put_no_document(self):
        self.pydantic_put_put_no_document(
            self.coverage1.document_id, user='moderator')

    def test_put_success_figures(self):
        body = {
            'message': 'Update figures',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-nw',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.coverage1.document_id),
            body, headers=headers, status=200)

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        self.assertEqual(coverage.coverage_type, 'fr-nw')

    def test_put_success_lang(self):
        body = {
            'message': 'Update lang',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.coverage1.document_id),
            body, headers=headers, status=200)

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        self.assertEqual(coverage.get_locale('en').title, 'New title')

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': quality_types[1],
                'locales': [
                    {'lang': 'es', 'title': 'Sureste de Francia'}
                ]
            }
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.coverage1.document_id),
            body, headers=headers, status=200)

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        self.assertEqual(coverage.get_locale('es').title,
                         'Sureste de Francia')

    def test_put_success_geometry(self):
        body = {
            'message': 'Update geometry',
            'document': {
                'document_id': self.coverage1.document_id,
                'version': self.coverage1.version,
                'coverage_type': 'fr-se',
                'quality': quality_types[1],
                'geometry': {
                    'version': self.coverage1.geometry.version,
                    'geom_detail':
                        '{"type":"Polygon","coordinates":'
                        '[[[668520.0,5728802.0],'
                        '[668520.0,5745465.0],'
                        '[689156.0,5745465.0],'
                        '[689156.0,5728802.0],'
                        '[668520.0,5728802.0]]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'South-East France',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.coverage1.document_id),
            body, headers=headers, status=200)

        self.session.expire_all()
        coverage = self.session.get(Coverage, self.coverage1.document_id)
        self.assertIsNotNone(coverage.geometry.geom_detail)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom_detail'))

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        self.assertIsInstance(polygon, Polygon)

    @staticmethod
    def _polygon_geojson():
        return (
            '{"type":"Polygon","coordinates":'
            '[[[668518.249382151,5728802.39591739],'
            '[668518.249382151,5745465.66808356],'
            '[689156.247019149,5745465.66808356],'
            '[689156.247019149,5728802.39591739],'
            '[668518.249382151,5728802.39591739]]]}'
        )

    def _add_test_data(self):
        self.coverage1 = Coverage(coverage_type='fr-se')

        self.locale_en = DocumentLocale(
            lang='en', title='South-East France')
        self.locale_fr = DocumentLocale(
            lang='fr', title='Sud-Est de la France')

        self.coverage1.locales.append(self.locale_en)
        self.coverage1.locales.append(self.locale_fr)

        self.coverage1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
        )

        self.session.add(self.coverage1)
        self.session.flush()

        # Coverage has no archive model — skip create_new_version

        self.coverage2 = Coverage(coverage_type='fr-nw')
        self.coverage2.locales.append(DocumentLocale(
            lang='en', title='North-West France'))
        self.coverage2.locales.append(DocumentLocale(
            lang='fr', title='Nord-Ouest de la France'))
        self.session.add(self.coverage2)
        self.session.flush()
