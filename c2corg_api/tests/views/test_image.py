import pytest
import json
from datetime import date
from unittest.mock import Mock, patch

from shapely.geometry import Point, shape

from c2corg_api.models.area import Area
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association
from c2corg_api.models.book import Book
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import (
    ArchiveDocumentLocale,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.feed import DocumentChange, update_feed_document_create
from c2corg_api.models.image import IMAGE_TYPE, ArchiveImage, Image
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.search import reset_search_index
from c2corg_api.tests.views import BaseDocumentTestRest, BaseTestRest
from c2corg_api.views.document import DocumentRest


class BaseTestImage(BaseDocumentTestRest):
    def _add_test_data(self):
        user_id = self.global_userids['contributor']

        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )

        self.locale_en = DocumentLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            document_topic=DocumentTopic(topic_id=1),
        )

        self.locale_fr = DocumentLocale(
            lang='fr', title='Mont Blanc du ciel', description='...'
        )

        self.image.locales.append(self.locale_en)
        self.image.locales.append(self.locale_fr)

        self.image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')

        self.session.add(self.image)
        self.session.flush()

        self.article1 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article1)
        self.session.flush()
        self._add_association(
            Association.create(
                parent_document=self.article1, child_document=self.image
            ),
            user_id,
        )

        self.book1 = Book(activities=['hiking'], book_types=['biography'])
        self.session.add(self.book1)
        self.session.flush()
        self._add_association(
            Association.create(parent_document=self.book1, child_document=self.image),
            user_id,
        )

        DocumentRest.create_new_version(self.image, user_id)

        self.image_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.image.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        self.image2 = Image(
            filename='image2.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image2)
        self.image3 = Image(
            filename='image3.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image3)
        self.image4 = Image(
            filename='image4.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='personal',
        )
        self.image4.locales.append(
            DocumentLocale(
                lang='en', title='Mont Blanc from the air', description='...'
            )
        )
        self.image4.locales.append(
            DocumentLocale(lang='fr', title='Mont Blanc du ciel', description='...')
        )
        self.session.add(self.image4)
        self.session.flush()
        DocumentRest.create_new_version(
            self.image3, self.global_userids['contributor2']
        )
        DocumentRest.create_new_version(self.image4, user_id)

        self._add_association(
            Association.create(parent_document=self.image, child_document=self.image2),
            user_id,
        )

        self.waypoint = Waypoint(
            waypoint_type='summit',
            elevation=4,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.waypoint.locales.append(
            WaypointLocale(
                lang='en', title='Mont Granier (en)', description='...', access='yep'
            )
        )
        self.session.add(self.waypoint)
        self.session.flush()
        update_feed_document_create(self.waypoint, user_id)
        self.session.flush()

        self.area = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='France')]
        )
        self.session.add(self.area)
        self.session.flush()

        self._add_association(Association.create(self.area, self.image), user_id)
        self.session.flush()

        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add(self.outing1)
        self.session.flush()
        self._add_association(
            Association.create(parent_document=self.outing1, child_document=self.image),
            user_id,
        )
        self._add_association(
            Association(
                parent_document_id=self.global_userids['contributor'],
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing1.document_id,
                child_document_type=OUTING_TYPE,
            ),
            user_id,
        )
        update_feed_document_create(self.outing1, user_id)
        self.session.flush()

    def _post_success_document(self, overrides={}):
        doc = {
            'filename': 'post_image.jpg',
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'geometry': {
                'id': 5678,
                'version': 6789,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
            'associations': {'waypoints': [{'document_id': self.waypoint.document_id}]},
        }
        doc.update(overrides)
        return doc

    def _validate_post_success(self, body, doc, check_wp=True):
        self._assert_geometry(body)

        version = doc.versions[0]

        archive_image = version.document_archive
        assert archive_image.activities == ['paragliding']
        assert archive_image.height == 1500

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == 'Some nice loop'

        archive_geometry = version.document_geometry_archive
        assert archive_geometry.version == doc.geometry.version
        assert archive_geometry.geom is not None

        if check_wp:
            # check that a link to the linked wp is created
            association_wp = self.session.get(
                Association, (self.waypoint.document_id, doc.document_id)
            )
            assert association_wp is not None

    def _assert_geometry(self, body):
        assert body.get('geometry') is not None
        geometry = body.get('geometry')
        assert geometry.get('version') is not None
        assert geometry.get('geom') is not None

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        assert isinstance(point, Point)
        assert point.x == pytest.approx(635956)
        assert point.y == pytest.approx(5723604)


class TestImageRest(BaseTestImage):
    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/images', IMAGE_TYPE, Image, ArchiveImage, ArchiveDocumentLocale
        )
        BaseTestImage.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        assert 'filename' in doc
        assert 'file_size' not in doc

    def test_get_collection_paginated(self):
        self.app.get('/images?offset=invalid', status=400)

        self.assertResultsEqual(self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}), [self.image4.document_id], 4
        )
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.image4.document_id, self.image3.document_id],
            4,
        )
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.image3.document_id, self.image2.document_id],
            4,
        )

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.image4.document_id, self.image.document_id],
            2,
        )

        self.assertResultsEqual(
            self.get_collection_search({'act': 'paragliding'}),
            [
                self.image4.document_id,
                self.image3.document_id,
                self.image2.document_id,
                self.image.document_id,
            ],
            4,
        )

    def test_get(self):
        body = self.get(self.image)
        self._assert_geometry(body)
        assert 'maps' not in body
        locale_en = self.get_locale('en', body.get('locales'))
        assert 1 == locale_en.get('topic_id')

        assert 'creator' in body
        creator = body.get('creator')
        assert self.global_userids['contributor'] == creator.get('user_id')

        assert 'associations' in body
        associations = body['associations']
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'xreports' in associations
        assert 'images' in associations
        assert 'users' in associations
        assert 'articles' in associations
        assert 'books' in associations
        assert 'areas' in associations
        assert 'outings' in associations

        linked_articles = associations.get('articles')
        assert len(linked_articles) == 1
        assert self.article1.document_id == linked_articles[0].get('document_id')

        linked_areas = associations.get('areas')
        assert len(linked_areas) == 1
        assert self.area.document_id == linked_areas[0].get('document_id')

        linked_books = associations.get('books')
        assert len(linked_books) == 1
        assert self.book1.document_id == linked_books[0].get('document_id')

        linked_outings = associations.get('outings')
        assert len(linked_outings) == 1
        assert self.outing1.document_id == linked_outings[0].get('document_id')

    def test_get_cooked(self):
        self.get_cooked(self.image)

    def test_get_cooked_with_defaulting(self):
        self.get_cooked_with_defaulting(self.image)

    def test_get_lang(self):
        self.get_lang(self.image)

    def test_get_new_lang(self):
        self.get_new_lang(self.image)

    def test_get_404(self):
        self.get_404()

    def test_get_edit(self):
        response = self.app.get(
            self._prefix + '/' + str(self.image.document_id) + '?e=1', status=200
        )
        body = response.json

        assert 'maps' not in body
        assert 'areas' not in body
        assert 'associations' in body
        associations = body['associations']
        assert 'waypoints' in associations
        assert 'routes' in associations
        assert 'images' in associations
        assert 'users' in associations
        assert 'articles' in associations

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        assert len(errors) == 1
        self.assertError(errors, 'filename', 'Required')

    def test_get_caching(self):
        self.get_caching(self.image)

    def test_get_info(self):
        body, locale = self.get_info(self.image, 'en')
        assert locale.get('lang') == 'en'

    def test_get_version(self):
        self.get_version(self.image, self.image_version)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_missing_title(self, post_mock):
        request_body = self._post_success_document()
        del request_body['locales'][0]['title']

        body, doc = self.post_success(request_body)
        assert doc.locales[0].title == ''

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_missing_title_none(self, post_mock):
        request_body = self._post_success_document()
        request_body['locales'][0]['title'] = None

        self.post_success(request_body)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_non_whitelisted_attribute(self, post_mock):
        body = {
            'filename': 'post_non_whitelisted.jpg',
            'activities': ['paragliding'],
            'image_type': 'collaborative',
            'height': 1500,
            'protected': True,
            'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_missing_filename(self):
        body_post = self._post_success_document()
        del body_post['filename']
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertError(errors, 'filename', 'Required')

    def test_post_duplicated_filename(self):
        body_post = self._post_success_document()
        body_post['filename'] = 'image.jpg'
        body = self.post_error(body_post)
        errors = body.get('errors')
        assert errors[0].get('description') == 'Unique'

    @patch(
        'c2corg_api.views.image.requests.post',
        return_value=Mock(status_code=500, reason='test error'),
    )
    def test_post_image_backend_error(self, post_mock):
        headers = self.add_authorization_header(username='contributor')
        r = self.app_post_json(
            self._prefix, self._post_success_document(), headers=headers, status=500
        )
        assert 'test error' in r.text

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_success(self, post_mock):
        waypoint_cache_key = self.session.get(
            CacheVersion, self.waypoint.document_id
        ).version
        body, doc = self.post_success(self._post_success_document())
        self._validate_post_success(body, doc)
        self.check_cache_version(self.waypoint.document_id, waypoint_cache_key + 1)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_no_permission_for_outing_association(self, post_mock):
        """Try to create an image with an association to an outing as a user
        who has no permission to add associations to that outing.
        """
        body_post = self._post_success_document(
            {'associations': {'outings': [{'document_id': self.outing1.document_id}]}}
        )

        headers = self.add_authorization_header(username='contributor2')
        response = self.app_post_json(
            self._prefix, body_post, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        self.assertError(
            body.get('errors'),
            'Bad Request',
            'no rights to modify associations with outing {}'.format(
                self.outing1.document_id
            ),
        )

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.image.version,
                'filename': 'put_wrong_document_id.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': -9999,
                'filename': 'put_wrong_document_version.jpg',
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_version(body, self.image.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': -9999,
                    }
                ],
            }
        }
        self.put_wrong_version(body, self.image.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        self.put_wrong_ids(body, self.image.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.image.document_id)

    def test_put_wrong_user(self):
        """Test that a non-moderator user who is not the creator of
        a personal image is not allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'filename': self.image4.filename,
                'activities': ['skitouring'],
                'image_type': 'personal',
                'quality': QualityTypes.draft,
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'A nice picture',
                        'version': self.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='contributor2')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id),
            body,
            headers=headers,
            status=403,
        )

    def test_put_good_user(self):
        """Test that a non-moderator user who is the creator of
        a personal image is allowed to modify it.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'filename': self.image4.filename,
                'quality': QualityTypes.draft,
                'activities': ['skitouring'],
                'image_type': 'personal',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'description': 'A nice picture',
                        'version': self.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'geometry': {
                    'version': self.image.geometry.version,
                    'geom': '{"type": "Point", "coordinates": [1, 2]}',
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'New description',
                        'version': self.locale_en.version,
                    }
                ],
                'associations': {
                    # association to outing is removed
                    'outings': [],
                    'waypoints': [{'document_id': self.waypoint.document_id}],
                },
            },
        }
        (body, image) = self.put_success_all(body, self.image, cache_version=3)

        assert image.height == 2000
        locale_en = image.get_locale('en')
        assert locale_en.description == 'New description'

        # version with lang 'en'
        versions = image.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Mont Blanc from the air'

        archive_document_en = version_en.document_archive
        assert archive_document_en.activities == ['paragliding']
        assert archive_document_en.height == 2000

        archive_geometry_en = version_en.document_geometry_archive
        assert archive_geometry_en.version == 2

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        assert archive_locale.title == 'Mont Blanc du ciel'

        # check that a link to the linked wp is created
        association_wp = self.session.get(
            Association, (self.waypoint.document_id, image.document_id)
        )
        assert association_wp is not None

    def test_put_no_permission_for_outing_association_removal(self):
        """Try to remove an association with an outing that the user has no
        permission to update the associations of.
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'associations': {
                    # association to outing is removed
                    'outings': [],
                    'waypoints': [{'document_id': self.waypoint.document_id}],
                },
            },
        }

        headers = self.add_authorization_header(username='contributor2')
        response = self.app_put_json(
            self._prefix + '/' + str(self.image.document_id),
            body,
            headers=headers,
            expect_errors=True,
            status=400,
        )

        body = response.json
        self.assertError(
            body.get('errors'),
            'Bad Request',
            'no rights to modify associations between '
            'document o ({}) and i ({})'.format(
                self.outing1.document_id, self.image.document_id
            ),
        )

    def test_put_success_as_contributor2(self):
        """Try to update an image with contributor2 who has no permission to
        change the association to the associated outing, but who can update
        the other fields/associations of the image.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        self.put_success_figures_only(body, self.image, user='contributor2')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 2000,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, image) = self.put_success_figures_only(body, self.image)

        assert image.height == 2000

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': 'New description',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        (body, image) = self.put_success_lang_only(body, self.image)

        assert image.get_locale('en').description == 'New description'

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale."""
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'es',
                        'title': 'Mont Blanc del cielo',
                        'description': '...',
                    }
                ],
            },
        }
        (body, image) = self.put_success_new_lang(body, self.image)

        assert image.get_locale('es').description == '...'

    def test_change_image_type_collaborative(self):
        """Test that a non-moderator user cannot change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id),
            body,
            headers=headers,
            status=400,
        )

    def test_change_image_type_copyright(self):
        """Test that a non-moderator user cannot change the image_type
        to copyright
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'copyright',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id),
            body,
            headers=headers,
            status=403,
        )

    def test_change_image_type_copyright_moderator(self):
        """Test that a moderator user can change the image_type
        to copyright
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'copyright',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_change_image_type_collaborative_moderator(self):
        """Test that a moderator can change the image_type
        of collaborative images
        """
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image.document_id,
                'version': self.image.version,
                'filename': self.image.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'personal',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='moderator')
        self.app_put_json(
            self._prefix + '/' + str(self.image.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_change_image_type_non_collaborative(self):
        """Test that non collaborative images can become collaborative"""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.image4.document_id,
                'version': self.image4.version,
                'filename': self.image4.filename,
                'quality': QualityTypes.draft,
                'activities': ['paragliding'],
                'image_type': 'collaborative',
                'height': 1500,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Mont Blanc from the air',
                        'description': '...',
                        'version': self.image4.get_locale('en').version,
                    }
                ],
            },
        }
        headers = self.add_authorization_header(username='contributor')
        self.app_put_json(
            self._prefix + '/' + str(self.image4.document_id),
            body,
            headers=headers,
            status=200,
        )

    def test_get_associations_history(self):
        self._get_association_logs(self.image)


class TestImageListRest(BaseTestImage):
    def setUp(self):  # noqa
        self.set_prefix_and_model(
            '/images', IMAGE_TYPE, Image, ArchiveImage, ArchiveDocumentLocale
        )
        BaseTestImage.setUp(self)
        self._add_test_data()

    def post_success(self, request_body, user='contributor'):
        response = self.app_post_json('/images/list', request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            '/images/list', request_body, headers=headers, status=200
        )

        body = response.json
        images = body.get('images')
        assert len(request_body['images']) == len(images)
        for image in images:
            (body, doc) = self._validate_document(image)

        return (body, doc)

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_success(self, post_mock):
        body = {'images': [self._post_success_document()]}
        body, doc = self.post_success(body)
        self._validate_post_success(body, doc)

        feed_change = self.get_feed_change(self.waypoint.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [self.global_userids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple(self, post_mock):
        body = {
            'images': [
                self._post_success_document(
                    {'filename': 'post_image2.jpg', 'locales': [{'lang': 'en'}]}
                ),
                self._post_success_document({'filename': 'post_image1.jpg'}),
            ]
        }
        body, doc = self.post_success(body)
        self._validate_post_success(body, doc)

        feed_change = self.get_feed_change(self.waypoint.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [self.global_userids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id
        assert feed_change.image3_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple_for_outing(self, post_mock):
        body = {
            'images': [
                self._post_success_document(
                    {
                        'filename': 'post_image1.jpg',
                        'associations': {
                            'outings': [{'document_id': self.outing1.document_id}]
                        },
                    }
                )
            ]
        }
        body, doc = self.post_success(body)
        self._validate_post_success(body, doc, check_wp=False)

        # check that a link to the linked image is created
        association_img = self.session.get(
            Association, (self.outing1.document_id, doc.document_id)
        )
        assert association_img is not None

        feed_change = self.get_feed_change(self.outing1.document_id)
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert feed_change.user_ids == [self.global_userids['contributor']]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is None
        assert feed_change.image3_id is None

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_multiple_as_contributor2(self, post_mock):
        user_id = self.global_userids['contributor2']
        body_request = {
            'images': [
                self._post_success_document({'filename': 'post_image1.jpg'}),
                self._post_success_document({'filename': 'post_image2.jpg'}),
            ]
        }
        body, doc = self.post_success(body_request, user='contributor2')
        self._validate_post_success(body, doc)

        feed_change = self.get_feed_change(
            self.waypoint.document_id, change_type='added_photos'
        )
        assert feed_change is not None
        assert feed_change.change_type == 'added_photos'
        assert feed_change.user_ids == [user_id]
        assert feed_change.image1_id is not None
        assert feed_change.image2_id is not None
        assert feed_change.image1_id != feed_change.image2_id

        q = (
            self.session.query(DocumentChange)
            .filter(DocumentChange.document_id == self.waypoint.document_id)
            .filter(DocumentChange.change_type == 'added_photos')
            .filter(DocumentChange.user_id == user_id)
        )

        assert 1 == q.count()

        # again upload images, and check that there is still only one entry
        body_request = {
            'images': [
                self._post_success_document({'filename': 'post_image3.jpg'}),
                self._post_success_document({'filename': 'post_image4.jpg'}),
            ]
        }
        self.post_success(body_request, user='contributor2')
        assert 1 == q.count()

        self.session.refresh(feed_change)
        assert feed_change.image3_id is not None
        assert feed_change.more_images

    @patch('c2corg_api.views.image.requests.post', return_value=Mock(status_code=200))
    def test_post_validation_error(self, post_mock):
        request_body = {
            'images': [
                self._post_success_document(
                    {
                        'geometry': {
                            'geom': '{"coordinates": [1, null], "type": "Point"}'
                        }
                    }
                )
            ]
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            '/images/list', request_body, headers=headers, status=400
        )

        body = response.json
        self.assertErrorsContain(body, 'images.0.geometry.geom')


class TestImageProxyRest(BaseTestRest):
    def setUp(self):  # noqa
        BaseTestRest.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.session.add(self.image)
        self.image2 = Image(
            filename='image.svg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.session.add(self.image2)
        self.session.flush()

    def test_get_not_exists(self):
        self.app.get('/images/proxy/{}'.format(999), status=404)

    def test_bad_size(self):
        resp = self.app.get(
            '/images/proxy/{}?size=badsize'.format(self.image.document_id), status=400
        )
        errors = resp.json.get('errors')
        assert 'invalid size' == errors[0].get('description')

    def test_success_without_size(self):
        resp = self.app.get(
            '/images/proxy/{}'.format(self.image.document_id), status=302
        )
        assert 'image.jpg' in resp.headers['Location']

    def test_success_with_size(self):
        resp = self.app.get(
            '/images/proxy/{}?size=BI'.format(self.image.document_id), status=302
        )
        assert 'imageBI.jpg' in resp.headers['Location']

    def test_svg_without_size(self):
        resp = self.app.get(
            '/images/proxy/{}'.format(self.image2.document_id), status=302
        )
        assert 'image.svg' in resp.headers['Location']

    def test_svg_with_size(self):
        resp = self.app.get(
            '/images/proxy/{}?size=BI'.format(self.image2.document_id), status=302
        )
        assert 'imageBI.jpg' in resp.headers['Location']

    def test_bad_extension(self):
        resp = self.app.get(
            '/images/proxy/{}?size=BI&extension=badextension'.format(
                self.image.document_id
            ),
            status=400,
        )
        errors = resp.json.get('errors')
        assert 'invalid extension' == errors[0].get('description')

    def test_format_without_size(self):
        resp = self.app.get(
            '/images/proxy/{}?extension=webp'.format(self.image.document_id), status=400
        )
        errors = resp.json.get('errors')
        assert 'invalid extension' == errors[0].get('description')

    def test_format_with_size(self):
        resp = self.app.get(
            '/images/proxy/{}?size=BI&extension=avif'.format(self.image.document_id),
            status=302,
        )
        assert 'imageBI.avif' in resp.headers['Location']
