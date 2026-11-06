import datetime

import pytest

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.views.test_feed import get_document_ids
from c2corg_api.views.document import create_new_version


class TestChangesDocumentRest:
    @pytest.fixture(autouse=True)
    def _setup_test_changes_document_rest(self, client, session, user_ids):
        self._prefix = '/documents/changes'

        contributor_id = user_ids['contributor']

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
        session.add(self.waypoint1)
        session.flush()
        create_new_version(self.waypoint1, contributor_id)
        session.flush()

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
        session.add(self.waypoint2)
        session.flush()
        create_new_version(self.waypoint2, contributor_id)
        session.flush()

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
        session.add(self.waypoint3)
        session.flush()
        create_new_version(self.waypoint3, contributor_id)
        session.flush()

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
        session.add(self.route1)
        session.flush()
        create_new_version(self.route1, contributor_id)
        session.flush()

        self.outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
        )
        session.add(self.outing)
        session.flush()
        create_new_version(self.outing, contributor_id)
        session.flush()

        self.profile2 = UserProfile(categories=['amateur'])
        session.add(self.profile2)
        session.flush()

    def test_counts(self, session):
        # besides these documents, the profiles of the global test users have
        # a version per locale (7, the contributor has two) and a history
        # entry each (6)
        version_count = session.query(DocumentVersion).count()
        assert 4 + 7 == version_count

        hist_meta_count = session.query(HistoryMetaData).count()
        assert 5 + 6 == hist_meta_count

    def test_get_changes(self, client):
        response = client.get(self._prefix, status=200)
        body = response.json

        assert 'total' not in body
        assert 'pagination_token' in body
        assert 'feed' in body

        feed = body['feed']
        assert 4 == len(feed)

        for doc in feed:
            assert doc['document']['type'] != 'o'
            assert doc['document']['type'] != 'u'

        # check that the change for the route (latest change) is listed first
        latest_change = feed[0]

        assert self.route1.document_id == latest_change['document']['document_id']

    def test_get_changes_empty(self, client):
        response = client.get(self._prefix + '?token=0', status=200)
        body = response.json

        assert 'pagination_token' not in body
        assert 'feed' in body

        feed = body['feed']
        assert 0 == len(feed)

    def test_get_changes_paginated(self, client):
        response = client.get(self._prefix + '?limit=2', status=200)
        body = response.json

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.route1.document_id, self.waypoint3.document_id]
        pagination_token = body['pagination_token']

        # last 2 changes
        response = client.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200
        )
        body = response.json

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.waypoint2.document_id, self.waypoint1.document_id]
        pagination_token = body['pagination_token']

        # empty response
        response = client.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200
        )
        body = response.json

        feed = body['feed']
        assert 0 == len(feed)

    def test_get_changes_pagination_invalid_format(self, client):
        response = client.get(self._prefix + '?token=invalid-token', status=422)
        assert ('query', 'token', 'invalid format') in invalid_parameters(response)

    def test_get_changes_userid_invalid_format(self, client):
        response = client.get(self._prefix + '?u=invalid-user_id', status=422)
        assert ('query', 'u', 'invalid u') in invalid_parameters(response)
