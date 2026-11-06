import json

import pytest
from shapely.geometry import Polygon, shape

from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.route import Route
from c2corg_api.models.topo_map import MAP_TYPE, ArchiveTopoMap, TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests import assert_required, auth_headers, send_json
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.scenarios import DocType
from c2corg_api.views.document import create_new_version

MAPS = DocType('/maps', MAP_TYPE, TopoMap, ArchiveTopoMap, ArchiveDocumentLocale)


class TestTopoMapRest:
    @pytest.fixture(autouse=True)
    def _setup_test_topo_map_rest(self, client, session, user_ids):
        self._add_test_data(session, user_ids)

    def test_get_collection(self, client, session):
        body = scenarios.get_collection(client, session, MAPS)
        doc = body['documents'][0]
        assert 'geometry' not in doc

    def test_get_collection_paginated(self, client, session):
        client.get('/maps?offset=invalid', status=422)

        scenarios.assert_results_equal(
            scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 0}),
            [],
            4,
        )

        scenarios.assert_results_equal(
            scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 1}),
            [self.map4.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(client, session, MAPS, {'offset': 0, 'limit': 2}),
            [self.map4.document_id, self.map3.document_id],
            4,
        )
        scenarios.assert_results_equal(
            scenarios.get_collection(client, session, MAPS, {'offset': 1, 'limit': 2}),
            [self.map3.document_id, self.map2.document_id],
            4,
        )

    def test_get_collection_lang(self, client):
        scenarios.get_collection_lang(client, MAPS)

    def test_get_collection_search(self, client, session):
        reset_search_index(session)

        scenarios.assert_results_equal(
            scenarios.get_collection_search(client, MAPS, {'l': 'en'}),
            [self.map4.document_id, self.map1.document_id],
            2,
        )

    def test_get(self, client):
        body = scenarios.get(client, MAPS, self.map1, title=self.locale_en.title)
        self._assert_geometry(body)
        assert 'maps' not in body
        # topo maps are not user content
        assert body['license'] is None

    def test_get_cooked(self, client):
        scenarios.get_cooked(client, MAPS, self.map1)

    def test_get_cooked_with_defaulting(self, client):
        scenarios.get_cooked_with_defaulting(client, MAPS, self.map1)

    def test_get_lang(self, client):
        scenarios.get_lang(client, MAPS, self.map1)

    def test_get_new_lang(self, client):
        scenarios.get_new_lang(client, MAPS, self.map1)

    def test_get_404(self, client):
        scenarios.get_404(client, MAPS)

    def test_get_caching(self, client):
        scenarios.get_caching(client, MAPS, self.map1)

    def test_get_info(self, client):
        body, locale = scenarios.get_info(client, MAPS, self.map1, 'en')
        assert locale.get('lang') == 'en'

    def test_post_not_moderator(self, client):
        headers = auth_headers(username='contributor')
        send_json(
            client,
            'post',
            MAPS.prefix,
            {},
            headers=headers,
            expect_errors=True,
            status=403,
        )

    def test_post_error(self, client):
        body = scenarios.post_error(client, MAPS, {}, user='moderator')
        errors = body.get('errors')
        assert len(errors) == 2
        assert_required(errors[0], 'locales')
        assert_required(errors[1], 'geometry')

    def test_post_missing_title(self, client):
        body_post = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
            },
            'locales': [{'lang': 'en'}],
        }
        scenarios.post_missing_title(client, MAPS, body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self, client, session):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'protected': True,
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
            },
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        scenarios.post_non_whitelisted_attribute(
            client, session, MAPS, body, user='moderator'
        )

    def test_post_missing_content_type(self, client):
        scenarios.post_missing_content_type(client, MAPS, {})

    def test_post_success(self, client, session):
        body = {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom_detail': '{"type":"Polygon","coordinates":[[[668518.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668518.249382151,5728802.39591739]]]}',  # noqa
            },
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
        }
        body, doc = scenarios.post_success(
            client, session, MAPS, body, user='moderator'
        )
        assert body['geometry'].get('geom_detail') is not None

        version = doc.versions[0]

        archive_map = version.document_archive
        assert archive_map.editor == 'IGN'
        assert archive_map.scale == '25000'
        assert archive_map.code == '3432OT'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.version == doc.geometry.version
        assert archive_geometry.geom_detail is not None
        assert archive_geometry.geom_detail is not None

        # check that a link for intersecting documents is created
        links = (
            session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.topo_map_id == doc.document_id)
            .order_by(TopoMapAssociation.document_id)
            .all()
        )
        assert len(links) == 2
        scenarios.check_cache_version(session, self.waypoint1.document_id, 2)
        scenarios.check_cache_version(session, self.route.document_id, 2)

    def test_put_wrong_document_id(self, client):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_document_id(client, MAPS, body, user='moderator')

    def test_put_wrong_document_version(self, client):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': -9999,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_version(
            client, MAPS, body, self.map1.document_id, user='moderator'
        )

    def test_put_wrong_locale_version(self, client):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
            }
        }
        scenarios.put_wrong_version(
            client, MAPS, body, self.map1.document_id, user='moderator'
        )

    def test_put_wrong_ids(self, client):
        body = {
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        scenarios.put_wrong_ids(
            client, MAPS, body, self.map1.document_id, user='moderator'
        )

    def test_put_no_document(self, client):
        scenarios.put_no_document(client, MAPS, self.map1.document_id, user='moderator')

    def test_put_success_all(self, client, session):
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
                    'geom_detail': '{"type":"Polygon","coordinates":[[[668519.249382151,5728802.39591739],[668518.249382151,5745465.66808356],[689156.247019149,5745465.66808356],[689156.247019149,5728802.39591739],[668519.249382151,5728802.39591739]]]}',  # noqa
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, map1) = scenarios.put_success_all(
            client,
            session,
            MAPS,
            body,
            self.map1,
            user='moderator',
            locale_fr=self.locale_fr,
        )

        assert map1.code == '3433OT'
        locale_en = map1.get_locale('en')
        assert locale_en.title == 'New title'

        # version with lang 'en'
        versions = map1.versions
        version_en = scenarios.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'New title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.scale == '25000'
        assert archive_document_en.code == '3433OT'

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = scenarios.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        assert archive_locale.title == "Lac d'Annecy"

        # check that the links to intersecting documents are updated
        links = (
            session.query(TopoMapAssociation)
            .filter(TopoMapAssociation.topo_map_id == self.map1.document_id)
            .all()
        )
        assert len(links) == 2
        scenarios.check_cache_version(session, self.waypoint1.document_id, 2)
        scenarios.check_cache_version(session, self.route.document_id, 2)
        # waypoint 2 is no longer associated, the cache key was incremented
        scenarios.check_cache_version(session, self.waypoint2.document_id, 2)

    def test_put_success_figures_only(self, client, session):
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
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, map1) = scenarios.put_success_figures_only(
            client, session, MAPS, body, self.map1, user='moderator'
        )

        assert map1.code == '3433OT'

    def test_put_success_lang_only(self, client, session):
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
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, map1) = scenarios.put_success_lang_only(
            client, session, MAPS, body, self.map1, user='moderator'
        )

        assert map1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self, client, session):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.map1.document_id,
                'version': self.map1.version,
                'quality': quality_types[1],
                'editor': 'IGN',
                'scale': '25000',
                'code': '3431OT',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        (body, map1) = scenarios.put_success_new_lang(
            client, session, MAPS, body, self.map1, user='moderator'
        )

        assert map1.get_locale('es').title == "Lac d'Annecy"

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom_detail') is not None

        geom = geometry.get('geom_detail')
        polygon = shape(json.loads(geom))
        assert isinstance(polygon, Polygon)

    def _add_test_data(self, session, user_ids):
        self.map1 = TopoMap(editor='IGN', scale='25000', code='3431OT')

        self.locale_en = DocumentLocale(lang='en', title="Lac d'Annecy")
        self.locale_fr = DocumentLocale(lang='fr', title="Lac d'Annecy")

        self.map1.locales.append(self.locale_en)
        self.map1.locales.append(self.locale_fr)

        self.map1.geometry = DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774 5706934,611774 5744215,'
            '642834 5744215,642834 5706934,611774 5706934))'
        )

        session.add(self.map1)
        session.flush()

        user_id = user_ids['contributor']
        create_new_version(self.map1, user_id)

        self.map2 = TopoMap(editor='IGN', scale='25000', code='3432OT')
        session.add(self.map2)
        self.map3 = TopoMap(editor='IGN', scale='25000', code='3433OT')
        session.add(self.map3)
        self.map4 = TopoMap(editor='IGN', scale='25000', code='3434OT')
        self.map4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.map4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        session.add(self.map4)
        session.flush()

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(677461.381691516 5740879.44638645)'
            ),
        )
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(693666.031687976 5741108.7574713)'
            ),
        )
        route_geom = 'SRID=3857;LINESTRING(668518 5728802, 668528 5728812)'
        self.route = Route(
            activities=['skitouring'], geometry=DocumentGeometry(geom_detail=route_geom)
        )

        session.add_all([self.waypoint1, self.waypoint2, self.route])
        session.add(TopoMapAssociation(document=self.waypoint2, topo_map=self.map1))
        session.flush()
