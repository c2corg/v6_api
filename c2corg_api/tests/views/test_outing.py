import datetime
import json
import unittest

from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.outing import Outing, ArchiveOuting, \
    ArchiveOutingLocale, OutingLocale, OUTING_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.search import reset_search_index
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, LineString

from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest
from shapely.geometry.point import Point


class TestOutingRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/outings', OUTING_TYPE, Outing, ArchiveOuting,
            ArchiveOutingLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        self.assertEqual(len(body['documents']), 4)
        doc1 = body['documents'][0]
        self.assertNotIn('frequentation', doc1)
        self.assertNotIn('duration_difficulties', doc1)

        doc4 = body['documents'][3]
        self.assertIn('author', doc4)
        author = doc4['author']
        self.assertEqual(author['username'], 'contributor')
        self.assertEqual(author['name'], 'Contributor')
        self.assertEqual(author['user_id'], self.global_userids['contributor'])
        self._add_test_data()

    # TODO check how these two requests are used (as part of advanced search?)
    @unittest.skip
    def test_get_collection_for_route(self):
        response = self.app.get(
            self._prefix + '?r=' + str(self.route.document_id), status=200)

        documents = response.json['documents']

        self.assertEqual(documents[0]['document_id'], self.outing.document_id)
        self.assertEqual(response.json['total'], 1)

    @unittest.skip
    def test_get_collection_for_waypoint(self):
        response = self.app.get(
            self._prefix + '?wp=' + str(self.waypoint.document_id), status=200)

        documents = response.json['documents']

        self.assertEqual(documents[0]['document_id'], self.outing.document_id)
        self.assertEqual(response.json['total'], 1)

    def test_get_collection_paginated(self):
        self.app.get("/outings?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.outing4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.outing4.document_id, self.outing3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.outing3.document_id, self.outing2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'ac': 'skitouring'})
        self.assertEqual(body.get('total'), 4)
        self.assertEqual(len(body.get('documents')), 4)

        body = self.get_collection_search({'wt': 'skitouring', 'limit': 2})
        self.assertEqual(body.get('total'), 4)
        self.assertEqual(len(body.get('documents')), 2)

        body = self.get_collection_search({'d': '2015-12-31,2016-01-02'})
        self.assertEqual(body.get('total'), 1)

    def test_get(self):
        body = self.get(self.outing)
        self.assertEqual(
            body.get('activities'), self.outing.activities)
        self._assert_geometry(body)
        self.assertNotIn('duration_difficulties', body)
        self.assertIn('frequentation', body)
        self.assertNotIn('maps', body)

        self.assertIn('associations', body)
        associations = body.get('associations')

        linked_routes = associations.get('routes')
        self.assertEqual(len(linked_routes), 1)
        self.assertEqual(
            self.route.document_id, linked_routes[0].get('document_id'))

        linked_users = associations.get('users')
        self.assertEqual(len(linked_users), 1)
        self.assertEqual(
            linked_users[0]['id'], self.global_userids['contributor'])

    def test_get_version(self):
        self.get_version(self.outing, self.outing_version)

    def test_get_lang(self):
        self.get_lang(self.outing)

    def test_get_new_lang(self):
        self.get_new_lang(self.outing)

    def test_get_404(self):
        self.get_404()

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 3)
        self.assertCorniceMissing(errors[0], 'outing')
        self.assertCorniceMissing(errors[1], 'route_id')
        self.assertCorniceMissing(errors[2], 'user_ids')

    def test_post_empty_activities_error(self):
        body = self.post_error({
            'outing': {
                'activities': [],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02'
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        })
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'Shorter than minimum length 1')
        self.assertEqual(errors[0].get('name'), 'outing.activities')

    def test_post_invalid_activity(self):
        body_post = {
            'outing': {
                'activities': ['cooking'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop'}
                ]
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        }
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'invalid value: cooking')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_missing_title(self):
        body_post = {
            'outing': {
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en'}
                ]
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        }
        body = self.post_missing_title(body_post, prefix='outing.')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'outing': {
                'activities': ['skitouring'],
                'protected': True,
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop',
                     'weather': 'sunny'}
                ]
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_missing_route_user_id(self):
        request_body = {
            'outing': {
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop',
                     'weather': 'sunny'}
                ]
            },
            # missing route_id,
            'user_ids': []
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(self._prefix, request_body,
                                      headers=headers, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceMissing(errors[0], 'route_id')
        self.assertEqual(
            errors[1].get('description'), 'Shorter than minimum length 1')
        self.assertEqual(errors[1].get('name'), 'user_ids')

    def test_post_invalid_route_id(self):
        request_body = {
            'outing': {
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop',
                     'weather': 'sunny'}
                ]
            },
            # invalid ids
            'route_id': self.waypoint.document_id,
            'user_ids': [-999]
        }
        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(self._prefix, request_body,
                                      headers=headers, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)

        self.assertEqual(
            errors[0].get('description'), 'route does not exist')
        self.assertEqual(errors[0].get('name'), 'route_id')
        self.assertEqual(
            errors[1].get('description'), 'user "-999" does not exist')
        self.assertEqual(errors[1].get('name'), 'user_ids')

    def test_post_success(self):
        body = {
            'outing': {
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'geometry': {
                    'id': 5678, 'version': 6789,
                    'geom_detail': '{"type": "LineString", "coordinates": ' +
                            '[[635956, 5723604], [635966, 5723644]]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop',
                     'weather': 'sunny'}
                ]
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body)
        self._assert_default_geometry(body)

        version = doc.versions[0]

        archive_outing = version.document_archive
        self.assertEqual(archive_outing.activities, ['skitouring'])
        self.assertEqual(archive_outing.elevation_max, 1500)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom_detail)

        association_route = self.session.query(Association).get(
            (self.route.document_id, doc.document_id))
        self.assertIsNotNone(association_route)

        association_route_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.route.document_id). \
            filter(AssociationLog.child_document_id ==
                   doc.document_id). \
            first()
        self.assertIsNotNone(association_route_log)

        association_user = self.session.query(Association).get(
            (self.global_userids['contributor'], doc.document_id))
        self.assertIsNotNone(association_user)

        association_user_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.global_userids['contributor']). \
            filter(AssociationLog.child_document_id ==
                   doc.document_id). \
            first()
        self.assertIsNotNone(association_user_log)

    def test_post_set_default_geom_from_route(self):
        body = {
            'outing': {
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Some nice loop',
                     'weather': 'sunny'}
                ]
            },
            'route_id': self.route.document_id,
            'user_ids': [self.global_userids['contributor']]
        }
        body, doc = self.post_success(body)
        self._assert_default_geometry(body, x=635961, y=5723624)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': -9999,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.outing.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.outing.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.outing.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.outing.document_id)

    def test_put_wrong_user(self):
        """Test that a non-moderator user who is not associated to the outing
        is not allowed to modify.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor2')
        self.app_put_json(
            self._prefix + '/' + str(self.outing.document_id), body,
            headers=headers, status=403)

    def test_put_good_user(self):
        """Test that a non-moderator user who is associated to the outing
        is allowed to modify.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.outing.document_id), body,
            headers=headers, status=200)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.outing.geometry.version,
                    'geom_detail':
                        '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635976, 5723654]]}'
                }
            }
        }
        (body, outing) = self.put_success_all(
            body, self.outing, user='moderator')

        # default geom is updated with the new track
        self._assert_default_geometry(body, x=635966, y=5723629)

        self.assertEquals(outing.elevation_max, 1600)
        locale_en = outing.get_locale('en')
        self.assertEquals(locale_en.description, '...')
        self.assertEquals(locale_en.weather, 'mostly sunny')

        # version with lang 'en'
        versions = outing.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')
        self.assertEqual(archive_locale.weather, 'mostly sunny')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['skitouring'])
        self.assertEqual(archive_document_en.elevation_max, 1600)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with lang 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')
        self.assertEqual(archive_locale.weather, 'grand beau')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, route) = self.put_success_figures_only(
            body, self.outing, user='moderator')

        self.assertEquals(route.elevation_max, 1600)

    def test_put_update_default_geom(self):
        """Tests that the default geometry can be updated directly.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'sunny',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.outing.geometry.version,
                    'geom_detail':
                        '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635976, 5723654]]}',
                    'geom':
                        '{"type": "Point", "coordinates": [635000, 5723000]}'
                }
            }
        }
        (body, route) = self.put_success_figures_only(
            body, self.outing, user='moderator')
        self._assert_default_geometry(body, x=635000, y=5723000)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'weather': 'mostly sunny',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, route) = self.put_success_lang_only(
            body, self.outing, user='moderator')

        self.assertEquals(route.get_locale('en').weather, 'mostly sunny')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.outing.document_id,
                'version': self.outing.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-01',
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'locales': [
                    {'lang': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...', 'weather': 'soleado'}
                ]
            }
        }
        (body, route) = self.put_success_new_lang(
            body, self.outing, user='moderator')

        self.assertEquals(route.get_locale('es').weather, 'soleado')

    def test_history(self):
        id = self.outing.document_id
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

    def test_history_no_lang(self):
        id = self.outing.document_id
        self.app.get('/document/%d/history/es' % id, status=404)

    def test_history_no_doc(self):
        self.app.get('/document/99999/history/es', status=404)

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom_detail'))

        geom = geometry.get('geom_detail')
        line = shape(json.loads(geom))
        self.assertIsInstance(line, LineString)
        self.assertAlmostEqual(line.coords[0][0], 635956)
        self.assertAlmostEqual(line.coords[0][1], 5723604)
        self.assertAlmostEqual(line.coords[1][0], 635966)
        self.assertAlmostEqual(line.coords[1][1], 5723644)

    def _assert_default_geometry(self, body, x=635961, y=5723624):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom'))

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        self.assertIsInstance(point, Point)
        self.assertAlmostEqual(point.x, x)
        self.assertAlmostEqual(point.y, y)

    def _add_test_data(self):
        self.outing = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1), elevation_max=1500,
            elevation_min=700, height_diff_up=800, height_diff_down=800
        )
        self.locale_en = OutingLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            weather='sunny')

        self.locale_fr = OutingLocale(
            lang='fr', title='Mont Blanc du ciel', description='...',
            weather='grand beau')

        self.outing.locales.append(self.locale_en)
        self.outing.locales.append(self.locale_fr)

        self.outing.geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)')

        self.session.add(self.outing)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.outing, user_id)
        self.outing_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.outing.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.outing2 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 1, 1)
        )
        self.session.add(self.outing2)
        self.outing3 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 1, 1)
        )
        self.session.add(self.outing3)
        self.outing4 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 1, 1)
        )
        self.outing4.locales.append(OutingLocale(
            lang='en', title='Mont Granier (en)', description='...'))
        self.outing4.locales.append(OutingLocale(
            lang='fr', title='Mont Granier (fr)', description='...'))
        self.session.add(self.outing4)

        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=4,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint.locales.append(WaypointLocale(
            lang='en', title='Mont Granier (en)', description='...',
            access='yep'))
        self.waypoint.locales.append(WaypointLocale(
            lang='fr', title='Mont Granier (fr)', description='...',
            access='ouai'))
        self.session.add(self.waypoint)
        self.session.flush()

        # add some associations
        self.route = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',  # noqa
                geom='SRID=3857;POINT(635961 5723624)'
        ))
        self.route.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            gear='paraglider', title_prefix='Main waypoint title'))
        self.route.locales.append(RouteLocale(
            lang='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider'))
        self.session.add(self.route)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route.document_id))
        self.session.add(Association(
            parent_document_id=self.route.document_id,
            child_document_id=self.outing.document_id))

        self.session.add(Association(
            parent_document_id=user_id,
            child_document_id=self.outing.document_id))
        self.session.flush()
