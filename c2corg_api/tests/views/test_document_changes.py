import datetime

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.tests.views.test_feed import get_document_ids
from c2corg_api.views.document import DocumentRest


class TestChangesDocumentRest(BaseTestRest):

    def setUp(self):
        super(TestChangesDocumentRest, self).setUp()
        self._prefix = '/documents/changes'

        contributor_id = self.global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles')
            ])
        self.session.add(self.waypoint1)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint1, contributor_id)
        self.session.flush()

        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint2)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint2, contributor_id)
        self.session.flush()

        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=4985,
            redirects_to=self.waypoint1.document_id,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add(self.waypoint3)
        self.session.flush()
        DocumentRest.create_new_version(self.waypoint3, contributor_id)
        self.session.flush()

        self.route1 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            main_waypoint_id=self.waypoint1.document_id,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route1)
        self.session.flush()
        DocumentRest.create_new_version(self.route1, contributor_id)
        self.session.flush()

        self.outing = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1), elevation_max=1500,
            elevation_min=700, height_diff_up=800, height_diff_down=800
        )
        self.session.add(self.outing)
        self.session.flush()
        DocumentRest.create_new_version(self.outing, contributor_id)
        self.session.flush()

        self.profile2 = UserProfile(categories=['amateur'])
        self.session.add(self.profile2)
        self.session.flush()

        version_count = self.session.query(DocumentVersion).count()
        self.assertEqual(4, version_count)

        hist_meta_count = self.session.query(HistoryMetaData).count()
        self.assertEqual(5, hist_meta_count)

    def test_get_changes(self):
        response = self.app.get(self._prefix, status=200)
        body = response.json

        self.assertNotIn('total', body)
        self.assertIn('pagination_token', body)
        self.assertIn('feed', body)

        feed = body['feed']
        self.assertEqual(4, len(feed))

        for doc in feed:
            self.assertNotEqual(doc['document']['type'], 'o')
            self.assertNotEqual(doc['document']['type'], 'u')

        # check that the change for the route (latest change) is listed first
        latest_change = feed[0]

        self.assertEqual(
            self.route1.document_id, latest_change['document']['document_id'])

    def test_get_changes_empty(self):
        response = self.app.get(self._prefix + '?token=0', status=200)
        body = response.json

        self.assertNotIn('pagination_token', body)
        self.assertIn('feed', body)

        feed = body['feed']
        self.assertEqual(0, len(feed))

    def test_get_changes_paginated(self):
        response = self.app.get(
            self._prefix + '?limit=2', status=200)
        body = response.json

        document_ids = get_document_ids(body)
        self.assertEqual(2, len(document_ids))
        self.assertEqual(document_ids, [self.route1.document_id,
                                        self.waypoint3.document_id])
        pagination_token = body['pagination_token']

        # last 2 changes
        response = self.app.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200)
        body = response.json

        document_ids = get_document_ids(body)
        self.assertEqual(2, len(document_ids))
        self.assertEqual(
            document_ids,
            [self.waypoint2.document_id, self.waypoint1.document_id])
        pagination_token = body['pagination_token']

        # empty response
        response = self.app.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(0, len(feed))

    def test_get_changes_pagination_invalid_format(self):
        response = self.app.get(
            self._prefix + '?token=invalid-token', status=400)
        self.assertError(response.json['errors'], 'token', 'invalid format')

    def test_get_changes_userid_invalid_format(self):
        response = self.app.get(
            self._prefix + '?u=invalid-user_id', status=400)
        self.assertError(response.json['errors'], 'u', 'invalid u')
