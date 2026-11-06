import datetime

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange, FilterArea, FollowedUser
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.tests import auth_headers, invalid_parameters


class BaseFeedTestRest:
    @pytest.fixture(autouse=True)
    def _setup_base_feed_test_rest(self, client, session, user_ids):
        self._prefix = '/feed'

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
        self.route = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            locales=[
                RouteLocale(
                    lang='fr',
                    title='Mont Blanc du ciel',
                    description='...',
                    summary='Ski',
                )
            ],
        )
        session.add(self.route)
        self.outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            frequentation='overcrowded',
            locales=[
                OutingLocale(
                    lang='en',
                    title='Mont Blanc : Face N!',
                    description='...',
                    weather='sunny',
                ),
                OutingLocale(
                    lang='fr',
                    title='Mont Blanc : Face N !',
                    description='...',
                    weather='beau',
                ),
            ],
        )
        session.add(self.outing)

        self.area1 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='France')]
        )
        self.area2 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='Suisse')]
        )

        session.add_all([self.area1, self.area2])
        session.flush()

        contributor_id = user_ids['contributor']
        contributor2_id = user_ids['contributor2']
        session.add(
            DocumentChange(
                time=datetime.datetime(2016, 1, 1, 12, 0, 0),
                user_id=contributor_id,
                change_type='created',
                document_id=self.waypoint1.document_id,
                document_type=WAYPOINT_TYPE,
                user_ids=[contributor_id],
                area_ids=[self.area1.document_id],
                langs=['fr'],
            )
        )
        session.add(
            DocumentChange(
                time=datetime.datetime(2016, 1, 1, 12, 0, 0),
                user_id=contributor2_id,
                change_type='created',
                document_id=self.waypoint2.document_id,
                document_type=WAYPOINT_TYPE,
                user_ids=[contributor2_id],
                area_ids=[self.area2.document_id],
                langs=['en'],
            )
        )
        session.add(
            DocumentChange(
                time=datetime.datetime(2016, 1, 1, 12, 1, 0),
                user_id=contributor_id,
                change_type='created',
                document_id=self.route.document_id,
                document_type=ROUTE_TYPE,
                user_ids=[contributor_id],
                activities=['hiking'],
                langs=['fr'],
                area_ids=[self.area1.document_id, self.area2.document_id],
            )
        )
        session.add(
            DocumentChange(
                time=datetime.datetime(2016, 1, 1, 12, 2, 0),
                user_id=contributor_id,
                change_type='created',
                document_id=self.outing.document_id,
                document_type=OUTING_TYPE,
                user_ids=[contributor_id, contributor2_id],
                activities=['skitouring'],
                langs=['en', 'fr'],
            )
        )
        session.flush()


class TestFeedRest(BaseFeedTestRest):
    def test_get_public_feed(self, client):
        response = client.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        assert 4 == len(feed)

        # check that the change for the outing (latest change) is listed first
        latest_change = feed[0]
        assert self.outing.document_id == latest_change['document']['document_id']

    def test_get_public_feed_ignoring_admin(self, client, user_ids):
        """Test that feed entries of admin users can be ignored."""
        client.registry.feed_admin_user_account_id = user_ids['contributor']
        response = client.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)

        # check that only the change of contributor2 is returned
        latest_change = feed[0]
        assert self.waypoint2.document_id == latest_change['document']['document_id']

    def test_get_public_feed_lang(self, client):
        response = client.get(self._prefix + '?pl=en', status=200)
        body = response.json

        feed = body['feed']
        assert 4 == len(feed)

        # check that only the 'en' locale is returned for the outing
        latest_change = feed[0]
        outing_locales = latest_change['document']['locales']
        assert 1 == len(outing_locales)
        assert 'en' == outing_locales[0]['lang']

    def test_get_public_feed_pagination_invalid_format(self, client):
        response = client.get(self._prefix + '?token=123,invalid-token', status=422)

        assert ('query', 'token', 'invalid format') in invalid_parameters(response)

    def test_get_public_feed_pagination(self, client):
        # first 2 changes
        response = client.get(self._prefix + '?limit=2', status=200)
        body = response.json

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.outing.document_id, self.route.document_id]
        pagination_token = body['pagination_token']

        # last 2 changes
        response = client.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200
        )
        body = response.json

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.waypoint1.document_id, self.waypoint2.document_id]
        pagination_token = body['pagination_token']

        # empty response
        response = client.get(
            self._prefix + '?limit=2&token=' + pagination_token, status=200
        )
        body = response.json

        document_ids = get_document_ids(body)
        assert 0 == len(document_ids)

    def test_get_public_feed_redirected_document(self, client, session):
        """Test that redirected documents are ignored."""
        self.waypoint1.redirects_to = self.waypoint2.document_id
        session.flush()

        response = client.get(self._prefix, status=200)
        body = response.json

        feed = body['feed']
        assert 3 == len(feed)


class TestPersonalFeedRest(BaseFeedTestRest):
    def test_get_feed_unauthenticated(self, client):
        """Get personal feed unauthenticated."""
        response = client.get('/personal-feed', status=403)
        # the message of Pyramid in production (without debug_authorization)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'Forbidden',
                'description': 'Authentication required',
            }
        ]

    def test_get_feed(self, client):
        """Get personal feed without custom filters (same as public feed)."""
        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 4 == len(feed)

        # check that the change for the outing (latest change) is listed first
        latest_change = feed[0]
        assert self.outing.document_id == latest_change['document']['document_id']

    def test_get_feed_activities_filter(self, client, session, user_ids):
        """Get personal feed with an activity filter."""
        # set an activity filter for the user
        user = session.get(User, user_ids['contributor'])
        user.feed_filter_activities = ['hiking']
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)

        assert self.route.document_id == feed[0]['document']['document_id']

    def test_get_feed_langs_filter(self, client, session, user_ids):
        """Get personal feed with a language filter."""
        # set a langs filter for the user
        user = session.get(User, user_ids['contributor'])
        user.feed_filter_langs = ['en', 'it']
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 2 == len(feed)

        # Last saved documents are listed first (anti-chronologically)
        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_areas_filter(self, client, session, user_ids):
        """Get personal feed with an area filter."""
        # set an area filter for the user
        session.add(
            FilterArea(
                area_id=self.area1.document_id,
                user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 2 == len(feed)

        assert self.route.document_id == feed[0]['document']['document_id']
        assert self.waypoint1.document_id == feed[1]['document']['document_id']

    def test_get_feed_areas_filter_ignoring_admin_changes(
        self, client, session, user_ids
    ):
        """Test that feed entries of admin users can be ignored."""
        client.registry.feed_admin_user_account_id = user_ids['contributor']
        # set an area filter for the user
        session.add(
            FilterArea(
                area_id=self.area1.document_id,
                user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 0 == len(feed)

    def test_get_feed_areas_and_activities_filter(self, client, session, user_ids):
        """Get personal feed with an area and activity filter."""
        # set an activity and are filter for the user
        user = session.get(User, user_ids['contributor'])
        user.feed_filter_activities = ['hiking']
        session.add(
            FilterArea(
                area_id=self.area1.document_id,
                user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)

        assert self.route.document_id == feed[0]['document']['document_id']

    def test_get_feed_followed_user_filter_ignored(self, client, session, user_ids):
        """Get personal feed with a followed user filter without area and
        activity filter (returns all changes). The followed users are ignored.
        """
        # follow a user
        session.add(
            FollowedUser(
                followed_user_id=user_ids['contributor2'],
                follower_user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 4 == len(feed)

    def test_get_feed_followed_user_filter_followed_only(
        self, client, session, user_ids
    ):
        """Get personal feed with a followed user and `feed_followed_only`."""
        # enable `feed_followed_only`
        user = session.get(User, user_ids['contributor'])
        user.feed_followed_only = True

        # follow a user
        session.add(
            FollowedUser(
                followed_user_id=user_ids['contributor2'],
                follower_user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 2 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_followed_user_and_activity_filter(
        self, client, session, user_ids
    ):
        """Get personal feed with a followed user and an activity filter."""
        # set activity filter
        user = session.get(User, user_ids['contributor'])
        user.feed_filter_activities = ['hiking']

        # follow a user
        session.add(
            FollowedUser(
                followed_user_id=user_ids['contributor2'],
                follower_user_id=user_ids['contributor'],
            )
        )
        session.flush()

        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 3 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.route.document_id == feed[1]['document']['document_id']
        assert self.waypoint2.document_id == feed[2]['document']['document_id']

    def test_get_feed_areas_filter_paginated(self, client, session, user_ids):
        """Get personal feed with an area filter (paginated)."""
        # set an area filter for the user
        session.add(
            FilterArea(
                area_id=self.area1.document_id,
                user_id=user_ids['contributor'],
            )
        )
        session.flush()

        # first page
        headers = auth_headers(username='contributor')
        response = client.get('/personal-feed?limit=1', status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)
        assert self.route.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # second page
        response = client.get(
            '/personal-feed?limit=1&token=' + pagination_token,
            status=200,
            headers=headers,
        )
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)
        assert self.waypoint1.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # empty response
        response = client.get(
            '/personal-feed?limit=1&token=' + pagination_token,
            status=200,
            headers=headers,
        )
        body = response.json

        feed = body['feed']
        assert 0 == len(feed)


class TestProfileFeedRest(BaseFeedTestRest):
    def test_get_feed_invalid_user_id(self, client):
        headers = auth_headers(username='contributor')
        client.get('/profile-feed?u=invalid-user-id', status=422, headers=headers)

    def test_get_feed_missing_user_id(self, client):
        headers = auth_headers(username='contributor')
        client.get('/profile-feed', status=422, headers=headers)

    def test_get_feed_non_existing_user(self, client):
        headers = auth_headers(username='contributor')
        client.get('/profile-feed?u=-1', status=404, headers=headers)

    def test_get_profile_contributor(self, client, user_ids):
        """Get profile feed for 'contributor'."""
        headers = auth_headers(username='contributor')
        user_id = user_ids['contributor']
        response = client.get(
            '/profile-feed?u=' + str(user_id), status=200, headers=headers
        )
        body = response.json

        feed = body['feed']
        assert 3 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.route.document_id == feed[1]['document']['document_id']
        assert self.waypoint1.document_id == feed[2]['document']['document_id']

    def test_get_profile_contributor2(self, client, user_ids):
        """Get profile feed for 'contributor2'."""
        headers = auth_headers(username='contributor')
        user_id = user_ids['contributor2']
        response = client.get(
            '/profile-feed?u=' + str(user_id), status=200, headers=headers
        )
        body = response.json

        feed = body['feed']
        assert 2 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_unauthenticated_public_profile(self, client, session, user_ids):
        """Get the public profile feed for 'contributor2'."""
        user_id = user_ids['contributor2']
        user = session.get(User, user_id)
        user.is_profile_public = True
        session.flush()

        response = client.get('/profile-feed?u=' + str(user_id), status=200)
        body = response.json

        feed = body['feed']
        assert 2 == len(feed)

    def test_get_feed_unauthenticated_non_public_profile(self, client, user_ids):
        """Try to get the non-public profile feed for 'contributor2'."""
        user_id = user_ids['contributor2']
        client.get('/profile-feed?u=' + str(user_id), status=403)

    def test_get_profile_contributor2_paginated(self, client, user_ids):
        """Get profile feed for 'contributor2' (paginated)."""
        headers = auth_headers(username='contributor')
        user_id = user_ids['contributor2']
        url = '/profile-feed?u=' + str(user_id) + '&limit=1'
        response = client.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # second page
        url = '/profile-feed?u=' + str(user_id) + '&limit=1&token=' + pagination_token
        response = client.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 1 == len(feed)
        assert self.waypoint2.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # empty response
        url = '/profile-feed?u=' + str(user_id) + '&limit=1&token=' + pagination_token
        response = client.get(url, status=200, headers=headers)
        body = response.json

        feed = body['feed']
        assert 0 == len(feed)


def get_document_ids(body):
    return [c['document']['document_id'] for c in body['feed']]
