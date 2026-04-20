"""
Tests for the FastAPI document-changes router
(``/v2/documents/changes``).
"""

from datetime import date

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


def get_document_ids(body):
    return [c['document']['document_id'] for c in body['feed']]


class TestDocumentChangesRouter(BaseTestCase):
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
        self.session.flush()
        create_new_version(self.waypoint1, contributor_id, db=self.session)
        self.session.flush()

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
        create_new_version(self.waypoint2, contributor_id, db=self.session)
        self.session.flush()

        self.waypoint3 = Waypoint(
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
        self.session.add(self.waypoint3)
        self.session.flush()
        create_new_version(self.waypoint3, contributor_id, db=self.session)
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
        self.session.flush()
        create_new_version(self.route1, contributor_id, db=self.session)
        self.session.flush()

        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
        )
        self.session.add(self.outing)
        self.session.flush()
        create_new_version(self.outing, contributor_id, db=self.session)
        self.session.flush()

        self.profile2 = UserProfile(categories=['amateur'])
        self.session.add(self.profile2)
        self.session.flush()

    def test_counts(self):
        version_count = self.session.query(DocumentVersion).count()
        assert 4 == version_count

        hist_meta_count = self.session.query(HistoryMetaData).count()
        assert 5 == hist_meta_count

    def test_get_changes(self):
        response = self.client.get('/v2/documents/changes')
        assert response.status_code == 200
        body = response.json()

        assert 'total' not in body
        assert 'pagination_token' in body
        assert 'feed' in body

        feed = body['feed']
        assert 4 == len(feed)

        for doc in feed:
            assert doc['document']['type'] != 'o'
            assert doc['document']['type'] != 'u'

        latest_change = feed[0]
        assert self.route1.document_id == latest_change['document']['document_id']

    def test_get_changes_empty(self):
        response = self.client.get('/v2/documents/changes?token=0')
        assert response.status_code == 200
        body = response.json()

        assert 'pagination_token' not in body
        assert 'feed' in body
        assert 0 == len(body['feed'])

    def test_get_changes_paginated(self):
        response = self.client.get('/v2/documents/changes?limit=2')
        assert response.status_code == 200
        body = response.json()

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.route1.document_id, self.waypoint3.document_id]
        pagination_token = body['pagination_token']

        # last 2 changes
        response = self.client.get(
            '/v2/documents/changes?limit=2&token=' + pagination_token
        )
        assert response.status_code == 200
        body = response.json()

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.waypoint2.document_id, self.waypoint1.document_id]
        pagination_token = body['pagination_token']

        # empty response
        response = self.client.get(
            '/v2/documents/changes?limit=2&token=' + pagination_token
        )
        assert response.status_code == 200
        body = response.json()
        assert 0 == len(body['feed'])

    def test_get_changes_pagination_invalid_format(self):
        response = self.client.get('/v2/documents/changes?token=invalid-token')
        assert response.status_code == 400
        body = response.json()
        errors = body['errors']
        found = any(
            e.get('name') == 'token' and 'invalid format' in e.get('description', '')
            for e in errors
        )
        assert found, body

    def test_get_changes_userid_invalid_format(self):
        response = self.client.get('/v2/documents/changes?u=invalid-user_id')
        assert response.status_code == 400
        body = response.json()
        errors = body['errors']
        found = any(
            e.get('name') == 'u' and 'invalid u' in e.get('description', '')
            for e in errors
        )
        assert found, body
