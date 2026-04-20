"""
Tests for the FastAPI document-merge router
(``/v2/documents/merge``).
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import or_

from c2corg_api.database import get_db
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.document import DocumentGeometry, DocumentLocale, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import DocumentChange, update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class TestDocumentMergeRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _post(self, body, expected_status):
        r = self.client.post(
            '/v2/documents/merge', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == expected_status, r.text
        return r

    def _add_test_data(self):
        contributor_id = global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles',
                )
            ],
        )
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
        self.session.add(self.waypoint2)
        self.session.flush()
        self.waypoint3 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            redirects_to=self.waypoint1.document_id,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
        self.session.add(self.waypoint3)
        self.waypoint4 = Waypoint(
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
        self.session.add(self.waypoint4)
        self.session.flush()

        self.route1 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            main_waypoint_id=self.waypoint1.document_id,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du ciel',
                    description='...',
                    summary='Ski',
                )
            ],
        )
        self.session.add(self.route1)
        self.route2 = Route(
            activities=['skitouring'],
            elevation_max=1400,
            elevation_min=700,
            main_waypoint_id=self.waypoint1.document_id,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du soleil',
                    description='...',
                    summary='Ski',
                )
            ],
        )
        self.session.add(self.route2)
        self.session.flush()

        create_new_version(self.waypoint1, contributor_id, db=self.session)
        update_feed_document_create(self.waypoint1, contributor_id)

        create_new_version(self.route1, contributor_id, db=self.session)
        update_feed_document_create(self.route1, contributor_id)

        create_new_version(self.route2, contributor_id, db=self.session)
        update_feed_document_create(self.route2, contributor_id)

        association = Association.create(
            parent_document=self.waypoint1, child_document=self.route1
        )
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))

        association = Association.create(
            parent_document=self.waypoint1, child_document=self.route2
        )
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))

        association = Association.create(
            parent_document=self.waypoint1, child_document=self.waypoint4
        )
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))

        association = Association.create(
            parent_document=self.waypoint2, child_document=self.waypoint4
        )
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))
        self.session.flush()

        self.image1 = Image(
            filename='image1.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air', description='...'
                )
            ],
        )
        self.session.add(self.image1)

        self.image2 = Image(
            filename='image2.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
            locales=[
                DocumentLocale(
                    lang='en', title='Mont Blanc from the air', description='...'
                )
            ],
        )
        self.session.add(self.image2)
        self.session.flush()

        create_new_version(self.image1, contributor_id, db=self.session)
        self.session.flush()

        # Create a second version of image1 with a different filename
        self.image1.filename = 'image1.1.jpg'
        self.session.flush()
        update_version(
            self.image1, contributor_id, 'changed filename', [UpdateType.FIGURES], []
        )
        self.session.flush()

        self.session.add(
            DocumentTag(
                document_id=self.route1.document_id,
                document_type=ROUTE_TYPE,
                user_id=contributor_id,
            )
        )
        self.session.add(
            DocumentTagLog(
                document_id=self.route1.document_id,
                document_type=ROUTE_TYPE,
                user_id=contributor_id,
                is_creation=True,
            )
        )
        self.session.flush()

    def check_cache_version(self, document_id, version):
        cache = self.session.get(CacheVersion, document_id)
        assert cache is not None
        assert cache is not None
        assert cache.version == version

    def test_non_unauthorized(self):
        r = self.client.post('/v2/documents/merge', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/documents/merge', json={}, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    def test_empty_body(self):
        self._post({}, 400)

    def test_same_document(self):
        self._post(
            {
                'source_document_id': self.waypoint1.document_id,
                'target_document_id': self.waypoint1.document_id,
            },
            400,
        )

    def test_non_existing_documents(self):
        self._post(
            {'source_document_id': -9999999, 'target_document_id': -99999999}, 400
        )

    def test_not_same_types(self):
        self._post(
            {
                'source_document_id': self.waypoint1.document_id,
                'target_document_id': self.route1.document_id,
            },
            400,
        )

    def test_already_merged(self):
        self._post(
            {
                'source_document_id': self.waypoint3.document_id,
                'target_document_id': self.waypoint2.document_id,
            },
            400,
        )
        self._post(
            {
                'source_document_id': self.waypoint2.document_id,
                'target_document_id': self.waypoint3.document_id,
            },
            400,
        )

    def test_merge_waypoint(self):
        self._post(
            {
                'source_document_id': self.waypoint1.document_id,
                'target_document_id': self.waypoint2.document_id,
            },
            200,
        )

        self.session.expire_all()

        # check associations transferred
        assoc_count = (
            self.session.query(Association)
            .filter(
                or_(
                    Association.parent_document_id == self.waypoint1.document_id,
                    Association.child_document_id == self.waypoint1.document_id,
                )
            )
            .count()
        )
        assert 0 == assoc_count

        assoc_log_count = (
            self.session.query(AssociationLog)
            .filter(
                or_(
                    AssociationLog.parent_document_id == self.waypoint1.document_id,
                    AssociationLog.child_document_id == self.waypoint1.document_id,
                )
            )
            .count()
        )
        assert 0 == assoc_log_count

        assoc_route = self.session.get(
            Association, (self.waypoint2.document_id, self.route1.document_id)
        )
        assert assoc_route is not None

        # check main waypoints transferred
        self.session.refresh(self.route1)
        assert self.route1.main_waypoint_id == self.waypoint2.document_id
        route_locale = self.route1.locales[0]
        assert 'Mont Blanc' == route_locale.title_prefix

        # check redirection
        self.session.refresh(self.waypoint1)
        assert self.waypoint1.redirects_to == self.waypoint2.document_id

        # check new version created
        new_source_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.waypoint1.document_id)
            .order_by(DocumentVersion.id.desc())
            .first()
        )
        assert new_source_version is not None
        assert new_source_version is not None
        assert (
            'merged with {}'.format(self.waypoint2.document_id)
            == new_source_version.history_metadata.comment
        )

        # check cache versions
        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.waypoint2.document_id, 3)
        self.check_cache_version(self.route1.document_id, 2)

        # check feed entry removed
        feed_count = (
            self.session.query(DocumentChange)
            .filter(DocumentChange.document_id == self.waypoint1.document_id)
            .count()
        )
        assert 0 == feed_count

    def test_tags(self):
        self._post(
            {
                'source_document_id': self.route1.document_id,
                'target_document_id': self.route2.document_id,
            },
            200,
        )

        self.session.expire_all()

        count = (
            self.session.query(DocumentTag)
            .filter(DocumentTag.document_id == self.route2.document_id)
            .count()
        )
        assert count == 1
        count = (
            self.session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == self.route2.document_id)
            .count()
        )
        assert count == 1

    def test_merge_image(self):
        """Merging images calls the image backend to delete the source
        image files (all archived filenames).
        """
        mock_response = MagicMock(status_code=200, content='')

        with (
            patch(
                'c2corg_api.routers.helpers.document_crud._load_settings_once',
                return_value=settings,
            ),
            patch('requests.post', return_value=mock_response) as mock_post,
        ):
            self._post(
                {
                    'source_document_id': self.image1.document_id,
                    'target_document_id': self.image2.document_id,
                },
                200,
            )
            assert mock_post.call_count == 1
            call_args = mock_post.call_args
            assert call_args[0][0] == settings['image_backend.url'] + '/delete'
            posted_data = call_args[1].get('data', {})
            posted_filenames = posted_data.get('filenames', [])
            assert 'image1.jpg' in posted_filenames
            assert 'image1.1.jpg' in posted_filenames

    def test_merge_image_error_deleting_files(self):
        """Merge succeeds even if the image backend returns an error
        when deleting the source image files.
        """
        mock_response = MagicMock(status_code=500, reason='Internal Server Error')

        with (
            patch(
                'c2corg_api.routers.helpers.document_crud._load_settings_once',
                return_value=settings,
            ),
            patch('requests.post', return_value=mock_response) as mock_post,
        ):
            self._post(
                {
                    'source_document_id': self.image1.document_id,
                    'target_document_id': self.image2.document_id,
                },
                200,
            )
            assert mock_post.call_count == 1
            call_args = mock_post.call_args
            posted_data = call_args[1].get('data', {})
            posted_filenames = posted_data.get('filenames', [])
            assert 'image1.jpg' in posted_filenames
            assert 'image1.1.jpg' in posted_filenames
