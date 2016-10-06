import datetime

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.outing import Outing, OutingLocale, OUTING_TYPE
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale, WAYPOINT_TYPE
from c2corg_api.tests.views import BaseTestRest


class TestFeedRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestFeedRest, self).setUp()
        self._prefix = '/feed'

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
        self.route = Route(
            document_id=534683,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route)
        self.outing = Outing(
            document_id=71175,
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1), frequentation='overcrowded',
            locales=[
                OutingLocale(
                    lang='en', title='Mont Blanc : Face N!',
                    description='...', weather='sunny'),
                OutingLocale(
                    lang='fr', title='Mont Blanc : Face N !',
                    description='...', weather='beau')
            ]
        )
        self.session.add(self.outing)
        self.session.flush()

        contributor_id = self.global_userids['contributor']
        contributor2_id = self.global_userids['contributor2']
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 0, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.waypoint1.document_id,
            document_type=WAYPOINT_TYPE, user_ids=[contributor_id]
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 0, 0),
            user_id=contributor2_id, change_type='created',
            document_id=self.waypoint2.document_id,
            document_type=WAYPOINT_TYPE, user_ids=[contributor2_id]
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 1, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.route.document_id,
            document_type=ROUTE_TYPE, user_ids=[contributor_id]
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 2, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.outing.document_id,
            document_type=OUTING_TYPE,
            user_ids=[contributor_id, contributor2_id]
        ))
        self.session.flush()

    def test_get_public_feed(self):
        response = self.app.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(4, len(feed))

        # check that the change for the outing (latest change) is listed first
        latest_change = feed[0]
        self.assertEqual(
            self.outing.document_id, latest_change['document']['document_id'])

    def test_get_public_feed_lang(self):
        response = self.app.get(self._prefix + '?pl=en', status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(4, len(feed))

        # check that only the 'en' locale is returned for the outing
        latest_change = feed[0]
        outing_locales = latest_change['document']['locales']
        self.assertEqual(1, len(outing_locales))
        self.assertEqual('en', outing_locales[0]['lang'])

    def test_get_public_feed_pagination_invalid_format(self):
        response = self.app.get(
            self._prefix + '?token=123,invalid-token', status=400)

        self.assertError(response.json['errors'], 'token', 'invalid format')

    def test_get_public_feed_pagination(self):
        # first 2 changes
        response = self.app.get(self._prefix + '?limit=2', status=200)
        body = response.json

        document_ids = get_document_ids(body)
        self.assertEqual(2, len(document_ids))
        self.assertEqual(
            document_ids, [self.outing.document_id, self.route.document_id])
        pagination_token = body['pagination_token']

        # last 2 changes
        response = self.app.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200)
        body = response.json

        document_ids = get_document_ids(body)
        self.assertEqual(2, len(document_ids))
        self.assertEqual(
            document_ids,
            [self.waypoint1.document_id, self.waypoint2.document_id])
        pagination_token = body['pagination_token']

        # empty response
        response = self.app.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200)
        body = response.json

        document_ids = get_document_ids(body)
        self.assertEqual(0, len(document_ids))


def get_document_ids(body):
    return [c['document']['document_id'] for c in body['feed']]
