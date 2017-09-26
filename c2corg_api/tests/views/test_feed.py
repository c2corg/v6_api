import datetime

from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange, FilterArea, FollowedUser
from c2corg_api.models.outing import Outing, OutingLocale, OUTING_TYPE
from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint, WaypointLocale, WAYPOINT_TYPE
from c2corg_api.tests.views import BaseTestRest


class BaseFeedTestRest(BaseTestRest):

    def setUp(self):  # noqa
        super(BaseFeedTestRest, self).setUp()
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
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route)
        self.outing = Outing(
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

        self.area1 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='France')
            ]
        )
        self.area2 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='Suisse')
            ]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.flush()

        contributor_id = self.global_userids['contributor']
        contributor2_id = self.global_userids['contributor2']
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 0, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.waypoint1.document_id,
            document_type=WAYPOINT_TYPE, user_ids=[contributor_id],
            area_ids=[self.area1.document_id], langs=['fr']
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 0, 0),
            user_id=contributor2_id, change_type='created',
            document_id=self.waypoint2.document_id,
            document_type=WAYPOINT_TYPE, user_ids=[contributor2_id],
            area_ids=[self.area2.document_id], langs=['en']
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 1, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.route.document_id,
            document_type=ROUTE_TYPE, user_ids=[contributor_id],
            activities=['hiking'], langs=['fr'],
            area_ids=[self.area1.document_id, self.area2.document_id]
        ))
        self.session.add(DocumentChange(
            time=datetime.datetime(2016, 1, 1, 12, 2, 0),
            user_id=contributor_id, change_type='created',
            document_id=self.outing.document_id,
            document_type=OUTING_TYPE,
            user_ids=[contributor_id, contributor2_id],
            activities=['skitouring'], langs=['en', 'fr']
        ))
        self.session.flush()


class TestFeedRest(BaseFeedTestRest):

    def test_get_public_feed(self):
        response = self.app.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(4, len(feed))

        # check that the change for the outing (latest change) is listed first
        latest_change = feed[0]
        self.assertEqual(
            self.outing.document_id, latest_change['document']['document_id'])

    def test_get_public_feed_ignoring_admin(self):
        """ Test that feed entries of admin users can be ignored.
        """
        self.app.app.registry.feed_admin_user_account_id = \
            self.global_userids['contributor']
        response = self.app.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))

        # check that only the change of contributor2 is returned
        latest_change = feed[0]
        self.assertEqual(
            self.waypoint2.document_id,
            latest_change['document']['document_id'])

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

    def test_get_public_feed_redirected_document(self):
        """ Test that redirected documents are ignored.
        """
        self.waypoint1.redirects_to = self.waypoint2.document_id
        self.session.flush()

        response = self.app.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(3, len(feed))


class TestPersonalFeedRest(BaseFeedTestRest):

    def test_get_feed_unauthenticated(self):
        """ Get personal feed unauthenticated.
        """
        self.app.get('/personal-feed', status=403)

    def test_get_feed(self):
        """ Get personal feed without custom filters (same as public feed).
        """
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(4, len(feed))

        # check that the change for the outing (latest change) is listed first
        latest_change = feed[0]
        self.assertEqual(
            self.outing.document_id, latest_change['document']['document_id'])

    def test_get_feed_activities_filter(self):
        """ Get personal feed with an activity filter.
        """
        # set an activity filter for the user
        user = self.session.query(User).get(self.global_userids['contributor'])
        user.feed_filter_activities = ['hiking']
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))

        self.assertEqual(
            self.route.document_id, feed[0]['document']['document_id'])

    def test_get_feed_langs_filter(self):
        """ Get personal feed with a language filter.
        """
        # set a langs filter for the user
        user = self.session.query(User).get(self.global_userids['contributor'])
        user.feed_filter_langs = ['en', 'it']
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(2, len(feed))

        # Last saved documents are listed first (anti-chronologically)
        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.waypoint2.document_id, feed[1]['document']['document_id'])

    def test_get_feed_areas_filter(self):
        """ Get personal feed with an area filter.
        """
        # set an area filter for the user
        self.session.add(FilterArea(
            area_id=self.area1.document_id,
            user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(2, len(feed))

        self.assertEqual(
            self.route.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.waypoint1.document_id, feed[1]['document']['document_id'])

    def test_get_feed_areas_filter_ignoring_admin_changes(self):
        """ Test that feed entries of admin users can be ignored.
        """
        self.app.app.registry.feed_admin_user_account_id = \
            self.global_userids['contributor']
        # set an area filter for the user
        self.session.add(FilterArea(
            area_id=self.area1.document_id,
            user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(0, len(feed))

    def test_get_feed_areas_and_activities_filter(self):
        """ Get personal feed with an area and activity filter.
        """
        # set an activity and are filter for the user
        user = self.session.query(User).get(self.global_userids['contributor'])
        user.feed_filter_activities = ['hiking']
        self.session.add(FilterArea(
            area_id=self.area1.document_id,
            user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))

        self.assertEqual(
            self.route.document_id, feed[0]['document']['document_id'])

    def test_get_feed_followed_user_filter_ignored(self):
        """ Get personal feed with a followed user filter without area and
        activity filter (returns all changes). The followed users are ignored.
        """
        # follow a user
        self.session.add(FollowedUser(
            followed_user_id=self.global_userids['contributor2'],
            follower_user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(4, len(feed))

    def test_get_feed_followed_user_filter_followed_only(self):
        """ Get personal feed with a followed user and `feed_followed_only`.
        """
        # enable `feed_followed_only`
        user = self.session.query(User).get(self.global_userids['contributor'])
        user.feed_followed_only = True

        # follow a user
        self.session.add(FollowedUser(
            followed_user_id=self.global_userids['contributor2'],
            follower_user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(2, len(feed))

        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.waypoint2.document_id, feed[1]['document']['document_id'])

    def test_get_feed_followed_user_and_activity_filter(self):
        """ Get personal feed with a followed user and an activity filter.
        """
        # set activity filter
        user = self.session.query(User).get(self.global_userids['contributor'])
        user.feed_filter_activities = ['hiking']

        # follow a user
        self.session.add(FollowedUser(
            followed_user_id=self.global_userids['contributor2'],
            follower_user_id=self.global_userids['contributor']))
        self.session.flush()

        headers = self.add_authorization_header(username='contributor')
        response = self.app.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(3, len(feed))

        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.route.document_id, feed[1]['document']['document_id'])
        self.assertEqual(
            self.waypoint2.document_id, feed[2]['document']['document_id'])

    def test_get_feed_areas_filter_paginated(self):
        """ Get personal feed with an area filter (paginated).
        """
        # set an area filter for the user
        self.session.add(FilterArea(
            area_id=self.area1.document_id,
            user_id=self.global_userids['contributor']))
        self.session.flush()

        # first page
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            '/personal-feed?limit=1', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))
        self.assertEqual(
            self.route.document_id, feed[0]['document']['document_id'])
        pagination_token = body['pagination_token']

        # second page
        response = self.app.get(
            '/personal-feed?limit=1&token=' + pagination_token, status=200,
            headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))
        self.assertEqual(
            self.waypoint1.document_id, feed[0]['document']['document_id'])
        pagination_token = body['pagination_token']

        # empty response
        response = self.app.get(
            '/personal-feed?limit=1&token=' + pagination_token, status=200,
            headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(0, len(feed))


class TestProfileFeedRest(BaseFeedTestRest):

    def test_get_feed_invalid_user_id(self):
        headers = self.add_authorization_header(username='contributor')
        self.app.get(
            '/profile-feed?u=invalid-user-id', status=400, headers=headers)

    def test_get_feed_missing_user_id(self):
        headers = self.add_authorization_header(username='contributor')
        self.app.get(
            '/profile-feed', status=400, headers=headers)

    def test_get_feed_non_existing_user(self):
        headers = self.add_authorization_header(username='contributor')
        self.app.get(
            '/profile-feed?u=-1', status=404, headers=headers)

    def test_get_profile_contributor(self):
        """ Get profile feed for 'contributor'.
        """
        headers = self.add_authorization_header(username='contributor')
        user_id = self.global_userids['contributor']
        response = self.app.get(
            '/profile-feed?u=' + str(user_id), status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(3, len(feed))

        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.route.document_id, feed[1]['document']['document_id'])
        self.assertEqual(
            self.waypoint1.document_id, feed[2]['document']['document_id'])

    def test_get_profile_contributor2(self):
        """ Get profile feed for 'contributor2'.
        """
        headers = self.add_authorization_header(username='contributor')
        user_id = self.global_userids['contributor2']
        response = self.app.get(
            '/profile-feed?u=' + str(user_id), status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(2, len(feed))

        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        self.assertEqual(
            self.waypoint2.document_id, feed[1]['document']['document_id'])

    def test_get_feed_unauthenticated_public_profile(self):
        """ Get the public profile feed for 'contributor2'.
        """
        user_id = self.global_userids['contributor2']
        user = self.session.query(User).get(user_id)
        user.is_profile_public = True
        self.session.flush()

        response = self.app.get('/profile-feed?u=' + str(user_id), status=200)
        body = response.json

        feed = body['feed']
        self.assertEqual(2, len(feed))

    def test_get_feed_unauthenticated_non_public_profile(self):
        """ Try to get the non-public profile feed for 'contributor2'.
        """
        user_id = self.global_userids['contributor2']
        self.app.get('/profile-feed?u=' + str(user_id), status=403)

    def test_get_profile_contributor2_paginated(self):
        """ Get profile feed for 'contributor2' (paginated).
        """
        headers = self.add_authorization_header(username='contributor')
        user_id = self.global_userids['contributor2']
        url = '/profile-feed?u=' + str(user_id) + '&limit=1'
        response = self.app.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))

        self.assertEqual(
            self.outing.document_id, feed[0]['document']['document_id'])
        pagination_token = body['pagination_token']

        # second page
        url = '/profile-feed?u=' + str(user_id) + '&limit=1&token=' + \
              pagination_token
        response = self.app.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(1, len(feed))
        self.assertEqual(
            self.waypoint2.document_id, feed[0]['document']['document_id'])
        pagination_token = body['pagination_token']

        # empty response
        url = '/profile-feed?u=' + str(user_id) + '&limit=1&token=' + \
              pagination_token
        response = self.app.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        self.assertEqual(0, len(feed))


def get_document_ids(body):
    return [c['document']['document_id'] for c in body['feed']]
