from datetime import date

from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_version
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    ArchiveXreport,
    ArchiveXreportLocale,
    Xreport,
    XreportLocale,
)
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import BaseDocumentTestRest
from c2corg_api.views.document import DocumentRest


class TestXreportRest(BaseDocumentTestRest):
    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/xreports', XREPORT_TYPE, Xreport, ArchiveXreport, ArchiveXreportLocale
        )
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        assert 'geometry' in doc

    def test_get_collection_paginated(self):
        self.app.get('/xreports?offset=invalid', status=400)

        self.assertResultsEqual(self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.xreport4.document_id],
            4,
        )
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.xreport4.document_id, self.xreport3.document_id],
            4,
        )
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.xreport3.document_id, self.xreport2.document_id],
            4,
        )

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.xreport4.document_id, self.xreport1.document_id],
            2,
        )

        self.assertResultsEqual(
            self.get_collection_search({'act': 'skitouring'}),
            [
                self.xreport4.document_id,
                self.xreport3.document_id,
                self.xreport2.document_id,
                self.xreport1.document_id,
            ],
            4,
        )

    def test_get(self):
        body = self.get(self.xreport1, user='moderator')
        assert 'xreport' not in body
        assert 'geometry' in body
        assert body.get('geometry') is None

        assert 'author' in body
        author = body.get('author')
        assert self.global_userids['contributor'] == author.get('user_id')

        associations = body['associations']
        assert 'images' in associations
        assert 'articles' in associations
        assert 'outings' in associations
        assert 'routes' in associations

        linked_images = associations.get('images')
        assert len(linked_images) == 0
        linked_articles = associations.get('articles')
        assert len(linked_articles) == 0
        linked_outings = associations.get('outings')
        assert len(linked_outings) == 1
        linked_routes = associations.get('routes')
        assert len(linked_routes) == 1

        assert body.get('event_activity') == self.xreport1.event_activity

        assert 'nb_participants' in body
        assert 'nb_impacted' in body
        assert 'event_type' in body
        assert body.get('event_type') == 'stone_ice_fall'
        assert 'date' in body
        assert body.get('date') == '2020-01-01'

        locale_en = self.get_locale('en', body.get('locales'))
        assert locale_en.get('place') == 'some place descrip. in english'
        locale_fr = self.get_locale('fr', body.get('locales'))
        assert locale_fr.get('place') == 'some place descrip. in french'

    def test_get_as_guest(self):
        body = self.get(self.xreport1, user=None)

        # common user should not see personal data in the xreport
        assert 'author_status' not in body
        assert 'activity_rate' not in body
        assert 'age' not in body
        assert 'gender' not in body
        assert 'previous_injuries' not in body
        assert 'autonomy' not in body

    def test_get_as_contributor_not_author(self):
        body = self.get(self.xreport1, user='contributor2')

        # common user should not see personal data in the xreport
        assert 'author_status' not in body
        assert 'activity_rate' not in body
        assert 'age' not in body
        assert 'gender' not in body
        assert 'previous_injuries' not in body
        assert 'autonomy' not in body

    def test_get_as_moderator(self):
        body = self.get(self.xreport1, user='moderator')

        # moderator can see personal data in the xreport
        assert 'author_status' in body
        assert 'activity_rate' in body
        assert 'age' in body
        assert 'gender' in body
        assert 'previous_injuries' in body
        assert 'autonomy' in body

    def test_get_cooked(self):
        self.get_cooked(self.xreport1)

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.xreport1)

    def test_get_lang(self):
        self.get_lang(self.xreport1, user='contributor')

    def test_get_new_lang(self):
        self.get_new_lang(self.xreport1, user='moderator')

    def test_get_404(self):
        self.get_404(user='moderator')

    def test_get_cache_headers(self):
        response = self.app.get(
            self._prefix + '/' + str(self.xreport1.document_id), status=200
        )
        headers = response.headers
        etag = headers.get('ETag')
        assert etag is not None

        assert response.headers.get('Cache-Control') == 'private'

    def test_get_version(self):
        self.get_version(self.xreport1, self.xreport1_version, user='contributor')

    def test_get_version_etag(self):
        auth_headers = self.add_authorization_header(username='contributor')
        url = '{0}/{1}/en/{2}'.format(
            self._prefix, str(self.xreport1.document_id), str(self.xreport1_version.id)
        )
        response = self.app.get(url, headers=auth_headers, status=200)

        # check that the ETag header is set
        headers = response.headers

        # TODO check etag as private
        etag = headers.get('ETag')
        assert etag is not None

        assert response.headers.get('Cache-Control') is None

        # then request the document again with the etag
        auth_headers['If-None-Match'] = etag
        response = self.app.get(url, status=304, headers=auth_headers)
        assert response.headers.get('Cache-Control') is None

    def test_get_version_caching(self):
        headers = self.add_authorization_header(username='contributor')
        url = '{0}/{1}/en/{2}'.format(
            self._prefix, str(self.xreport1.document_id), str(self.xreport1_version.id)
        )
        cache_key = '{0}-{1}'.format(
            get_cache_key(self.xreport1.document_id, 'en', XREPORT_TYPE),
            self.xreport1_version.id,
        )

        cache_value = cache_document_version.get(cache_key)
        assert cache_value == NO_VALUE

        # check that the response is cached
        self.app.get(url, headers=headers, status=200)

        cache_value = cache_document_version.get(cache_key)
        assert cache_value != NO_VALUE

        # check that values are returned from the cache
        fake_cache_value = {'document': 'fake doc'}
        cache_document_version.set(cache_key, fake_cache_value)

        response = self.app.get(url, headers=headers, status=200)
        body = response.json
        assert body == fake_cache_value

    def test_get_caching(self):
        self.get_caching(self.xreport1)

    def test_get_info(self):
        _, locale = self.get_info(self.xreport1, 'en')
        assert locale.get('lang') == 'en'

    def test_get_info_best_lang(self):
        _, locale = self.get_info(self.xreport1, 'es')
        assert locale.get('lang') == 'fr'

    def test_get_info_404(self):
        self.get_info_404()

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        assert len(errors) == 1
        self.assertError(errors, 'event_activity', 'Required')

    def test_post_missing_title(self):
        body_post = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'locales': [{'lang': 'en'}],
        }
        self.post_missing_title(body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'protected': True,
            'locales': [
                {
                    'lang': 'en',
                    'place': 'some place description',
                    'title': "Lac d'Annecy",
                }
            ],
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_wrong_geom_type(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'associations': {
                'images': [{'document_id': self.image2.document_id}],
                'articles': [{'document_id': self.article2.document_id}],
            },
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom': '{"type": "LineString", "coordinates": '
                + '[[635956, 5723604], [635966, 5723644]]}',
            },
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        errors = self.post_wrong_geom_type(body)
        assert (
            errors[0]['description']
            == "Invalid geometry type. Expected: ['POINT']. Got: LINESTRING."
        )

    def test_post_outdated_attributes_error(self):
        outdated_attributes = [
            # api not checking additional parameters,
            # nb_outings raises no error
            # ('nb_outings', 'nb_outings_9'),
            ('autonomy', 'initiator'),
            ('activity_rate', 'activity_rate_10'),
            ('event_type', 'roped_fall'),
            ('event_activity', 'hiking'),
        ]
        for key, value in outdated_attributes:
            body = {
                'document_id': 123456,
                'event_activity': 'skitouring',
                'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
            }
            body[key] = value
            body = self.post_error(body, user='moderator')
            errors = body.get('errors')
            assert len(errors) == 1
            assert errors[0].get('name') == key
            desc = errors[0].get('description')
            assert 'is not one of' in desc or 'Input should be' in desc, (
                'Unexpected enum error description: %s' % desc
            )

    def test_post_success(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'nb_outings': 'nb_outings9',
            'autonomy': 'autonomous',
            'activity_rate': 'activity_rate_m2',
            'supervision': 'professional_supervision',
            'qualification': 'federal_trainer',
            'associations': {
                'images': [{'document_id': self.image2.document_id}],
                'articles': [{'document_id': self.article2.document_id}],
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        body, doc = self.post_success(body, user='moderator', validate_with_auth=True)
        version = doc.versions[0]

        archive_xreport = version.document_archive
        assert archive_xreport.event_activity == 'skitouring'
        assert archive_xreport.event_type == 'stone_ice_fall'
        assert archive_xreport.nb_participants == 5
        assert not hasattr(archive_xreport, 'nb_outings')
        assert archive_xreport.autonomy == 'autonomous'
        assert archive_xreport.activity_rate == 'activity_rate_m2'
        assert archive_xreport.supervision == 'professional_supervision'
        assert archive_xreport.qualification == 'federal_trainer'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        # check if geometry is stored in database afterwards
        assert doc.geometry is not None

        # check that a link to the associated waypoint is created
        association_img = self.session.get(
            Association, (doc.document_id, self.image2.document_id)
        )
        assert association_img is not None

        association_img_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.image2.document_id)
            .first()
        )
        assert association_img_log is not None

        # check that a link to the associated xreport is created
        association_art = self.session.get(
            Association, (doc.document_id, self.article2.document_id)
        )
        assert association_art is not None

        association_art_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert association_art_log is not None

    def test_post_as_contributor_and_get_as_author(self):
        body_post = {
            'document_id': 111,
            'version': 1,
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 666,
            'nb_impacted': 666,
            'locales': [
                # {'title': 'Lac d\'Annecy', 'lang': 'fr'},
                {'title': "Lac d'Annecy", 'lang': 'en'}
            ],
        }

        # create document (POST uses GET schema inside validation)
        body_post, doc = self.post_success(body_post, user='contributor')

        # the contributor is successfully set as author in DB
        user_id = self.global_userids['contributor']
        version = doc.versions[0]
        meta_data = version.history_metadata
        assert meta_data.user_id == user_id

        # authorized contributor can see personal data in the xreport
        body = self.get(doc, user='contributor', ignore_checks=True)
        assert 'xreport' not in body

        assert 'author_status' in body
        assert 'activity_rate' in body
        assert 'age' in body
        assert 'gender' in body
        assert 'previous_injuries' in body
        assert 'autonomy' in body

    def test_post_anonymous(self):
        self.app.app.registry.anonymous_user_id = self.global_userids['moderator']
        body_post = {
            'document_id': 111,
            'version': 1,
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 666,
            'nb_impacted': 666,
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
            'anonymous': True,
        }

        body_post, doc = self.post_success(body_post, user='contributor')

        # Check that the contributor is not set as author
        user_id = self.global_userids['contributor']
        version = doc.versions[0]
        meta_data = version.history_metadata
        assert meta_data.user_id != user_id
        assert meta_data.user_id == self.global_userids['moderator']

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': -9999,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_version(body, self.xreport1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
            }
        }
        self.put_wrong_version(body, self.xreport1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_ids(body, self.xreport1.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.xreport1.document_id, user='moderator')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'associations': {
                    'images': [{'document_id': self.image2.document_id}],
                    'articles': [{'document_id': self.article2.document_id}],
                },
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'place': 'some NEW place descrip. in english',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, xreport1) = self.put_success_all(
            body, self.xreport1, user='moderator', cache_version=3
        )

        assert xreport1.event_activity == 'skitouring'
        locale_en = xreport1.get_locale('en')
        assert locale_en.title == 'New title'

        # version with lang 'en'
        versions = xreport1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'New title'
        assert archive_locale.place == 'some NEW place descrip. in english'

        archive_document_en = version_en.document_archive
        assert archive_document_en.event_activity == 'skitouring'
        assert archive_document_en.event_type == 'stone_ice_fall'
        assert archive_document_en.nb_participants == 333
        assert archive_document_en.nb_impacted == 666

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        assert archive_locale.title == "Lac d'Annecy"

        # check if geometry is stored in database afterwards
        assert xreport1.geometry is not None
        # check that a link to the associated image is created
        association_img = self.session.get(
            Association, (xreport1.document_id, self.image2.document_id)
        )
        assert association_img is not None

        association_img_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == xreport1.document_id)
            .filter(AssociationLog.child_document_id == self.image2.document_id)
            .first()
        )
        assert association_img_log is not None

        # check that a link to the associated article is created
        association_main_art = self.session.get(
            Association, (xreport1.document_id, self.article2.document_id)
        )
        assert association_main_art is not None

        association_art_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == xreport1.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert association_art_log is not None

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'place': 'some place descrip. in english',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, xreport1) = self.put_success_figures_only(
            body, self.xreport1, user='moderator'
        )

        assert xreport1.event_activity == 'skitouring'

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'date': '2020-01-01',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, xreport1) = self.put_success_lang_only(
            body, self.xreport1, user='moderator'
        )

        assert xreport1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'date': '2020-01-01',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        (body, xreport1) = self.put_success_new_lang(
            body, self.xreport1, user='moderator'
        )

        assert xreport1.get_locale('es').title == "Lac d'Annecy"

    def test_put_as_author(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'sport_climbing',  # changed
                'event_type': 'person_fall',  # changed
                'age': 90,  # PERSONAL DATA CHANGED
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }

        (body, xreport1) = self.put_success_all(
            body, self.xreport1, user='contributor', cache_version=2
        )

        # version with lang 'en'
        versions = xreport1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Another final EN title'

        archive_document_en = version_en.document_archive
        assert archive_document_en.event_activity == 'sport_climbing'
        assert archive_document_en.event_type == 'person_fall'
        assert archive_document_en.age == 90

    def test_put_as_associated_user(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'alpine_climbing',  # changed
                'event_type': 'crevasse_fall',  # changed
                'age': 25,  # PERSONAL DATA CHANGED
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Renamed title by assoc. user',
                        'version': self.locale_en.version,
                    }
                ],
                'associations': {  # added associations
                    'articles': [{'document_id': self.article2.document_id}],
                    'routes': [{'document_id': self.route3.document_id}],
                },
            },
        }

        (body, xreport1) = self.put_success_all(
            body, self.xreport1, user='contributor3', cache_version=3
        )

        # version with lang 'en'
        versions = xreport1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Renamed title by assoc. user'

        archive_document_en = version_en.document_archive
        assert archive_document_en.event_activity == 'alpine_climbing'
        assert archive_document_en.event_type == 'crevasse_fall'
        assert archive_document_en.age == 25

    def test_put_as_non_author(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport4.document_id,
                'version': self.xreport4.version,
                'quality': QualityTypes.draft,
                'event_activity': 'sport_climbing',
                'event_type': 'person_fall',
                'age': 90,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }

        headers = self.add_authorization_header(username='contributor2')
        response = self.app_put_json(
            self._prefix + '/' + str(self.xreport4.document_id),
            body,
            headers=headers,
            status=403,
        )

        body = response.json
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Forbidden'

    def test_get_associations_history(self):
        self._get_association_logs(self.xreport1)

    def _add_test_data(self):
        self.xreport1 = Xreport(
            event_activity='skitouring',
            event_type='stone_ice_fall',
            date=date(2020, 1, 1),
        )
        self.locale_en = XreportLocale(
            lang='en', title="Lac d'Annecy", place='some place descrip. in english'
        )
        self.locale_fr = XreportLocale(
            lang='fr', title="Lac d'Annecy", place='some place descrip. in french'
        )

        self.xreport1.locales.append(self.locale_en)
        self.xreport1.locales.append(self.locale_fr)

        self.session.add(self.xreport1)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.xreport1, user_id)
        self.xreport1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.xreport1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        user_id3 = self.global_userids['contributor3']
        self._add_association(
            Association(
                parent_document_id=user_id3,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.xreport1.document_id,
                child_document_type=XREPORT_TYPE,
            ),
            user_id,
        )

        self.xreport2 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            date=date(2021, 1, 1),
        )
        self.session.add(self.xreport2)
        self.xreport3 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            date=date(2018, 1, 1),
        )
        self.session.add(self.xreport3)
        self.xreport4 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            nb_impacted=5,
            age=50,
        )
        self.xreport4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.xreport4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        self.session.add(self.xreport4)

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article2)
        self.session.flush()

        self.image2 = Image(
            filename='image2.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image2)
        self.session.flush()

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint2)
        self.session.flush()

        self.outing3 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 2),
        )
        self.session.add(self.outing3)
        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=500,
            height_diff_down=500,
            durations=['1'],
        )
        self.session.add(self.route3)
        self.session.flush()

        self._add_association(
            Association.create(
                parent_document=self.outing3, child_document=self.xreport1
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.route3, child_document=self.xreport1
            ),
            user_id,
        )
        self.session.flush()
