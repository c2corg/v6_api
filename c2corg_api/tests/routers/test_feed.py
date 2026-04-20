"""
Tests for the FastAPI feed router (``/v2/feed``, ``/v2/personal-feed``,
``/v2/profile-feed``).

Mirrors ``c2corg_api/tests/views/test_feed.py``.
"""

from datetime import date, datetime

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange, FilterArea, FollowedUser
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.routers.feed import configure_feed_router
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


def get_document_ids(body):
    return [c['document']['document_id'] for c in body['feed']]


class BaseFeedTestRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_feed_router(settings)
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

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _add_test_data(self):
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
        self.session.add(self.route)
        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
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
        self.session.add(self.outing)

        self.area1 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='France')]
        )
        self.area2 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='Suisse')]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.flush()

        contributor_id = global_userids['contributor']
        contributor2_id = global_userids['contributor2']
        self.session.add(
            DocumentChange(
                time=datetime(2016, 1, 1, 12, 0, 0),
                user_id=contributor_id,
                change_type='created',
                document_id=self.waypoint1.document_id,
                document_type=WAYPOINT_TYPE,
                user_ids=[contributor_id],
                area_ids=[self.area1.document_id],
                langs=['fr'],
            )
        )
        self.session.add(
            DocumentChange(
                time=datetime(2016, 1, 1, 12, 0, 0),
                user_id=contributor2_id,
                change_type='created',
                document_id=self.waypoint2.document_id,
                document_type=WAYPOINT_TYPE,
                user_ids=[contributor2_id],
                area_ids=[self.area2.document_id],
                langs=['en'],
            )
        )
        self.session.add(
            DocumentChange(
                time=datetime(2016, 1, 1, 12, 1, 0),
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
        self.session.add(
            DocumentChange(
                time=datetime(2016, 1, 1, 12, 2, 0),
                user_id=contributor_id,
                change_type='created',
                document_id=self.outing.document_id,
                document_type=OUTING_TYPE,
                user_ids=[contributor_id, contributor2_id],
                activities=['skitouring'],
                langs=['en', 'fr'],
            )
        )
        self.session.flush()


class TestFeedRouter(BaseFeedTestRouter):
    def test_get_public_feed(self):
        r = self.client.get('/v2/feed')
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 4 == len(feed)

        # latest change (outing) should be listed first
        latest_change = feed[0]
        assert self.outing.document_id == latest_change['document']['document_id']

    def test_get_public_feed_ignoring_admin(self):
        """Test that feed entries of admin users can be ignored."""
        import c2corg_api.routers.feed as feed_mod

        feed_mod._feed_admin_user_account_id = global_userids['contributor']
        try:
            r = self.client.get('/v2/feed')
            assert r.status_code == 200
            body = r.json()

            feed = body['feed']
            assert 1 == len(feed)

            latest_change = feed[0]
            assert (
                self.waypoint2.document_id == latest_change['document']['document_id']
            )
        finally:
            feed_mod._feed_admin_user_account_id = None

    def test_get_public_feed_lang(self):
        r = self.client.get('/v2/feed?pl=en')
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 4 == len(feed)

        # check that only the 'en' locale is returned for the outing
        latest_change = feed[0]
        outing_locales = latest_change['document']['locales']
        assert 1 == len(outing_locales)
        assert 'en' == outing_locales[0]['lang']

    def test_get_public_feed_pagination_invalid_format(self):
        r = self.client.get('/v2/feed?token=123,invalid-token')
        assert r.status_code == 400

    def test_get_public_feed_pagination(self):
        # first 2 changes
        r = self.client.get('/v2/feed?limit=2')
        assert r.status_code == 200
        body = r.json()

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.outing.document_id, self.route.document_id]
        pagination_token = body['pagination_token']

        # last 2 changes
        r = self.client.get('/v2/feed?limit=2&token=' + pagination_token)
        assert r.status_code == 200
        body = r.json()

        document_ids = get_document_ids(body)
        assert 2 == len(document_ids)
        assert document_ids == [self.waypoint1.document_id, self.waypoint2.document_id]
        pagination_token = body['pagination_token']

        # empty response
        r = self.client.get('/v2/feed?limit=2&token=' + pagination_token)
        assert r.status_code == 200
        body = r.json()

        document_ids = get_document_ids(body)
        assert 0 == len(document_ids)

    def test_get_public_feed_redirected_document(self):
        """Test that redirected documents are ignored."""
        self.waypoint1.redirects_to = self.waypoint2.document_id
        self.session.flush()

        r = self.client.get('/v2/feed')
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 3 == len(feed)


class TestPersonalFeedRouter(BaseFeedTestRouter):
    def test_get_feed_unauthenticated(self):
        r = self.client.get('/v2/personal-feed')
        assert r.status_code == 403

    def test_get_feed(self):
        """Get personal feed without custom filters (same as public feed)."""
        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 4 == len(feed)

        latest_change = feed[0]
        assert self.outing.document_id == latest_change['document']['document_id']

    def test_get_feed_activities_filter(self):
        """Get personal feed with an activity filter."""
        user = self.session.get(User, global_userids['contributor'])
        assert user is not None
        user.feed_filter_activities = ['hiking']
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.route.document_id == feed[0]['document']['document_id']

    def test_get_feed_langs_filter(self):
        """Get personal feed with a language filter."""
        user = self.session.get(User, global_userids['contributor'])
        assert user is not None
        user.feed_filter_langs = ['en', 'it']
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 2 == len(feed)
        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_areas_filter(self):
        """Get personal feed with an area filter."""
        self.session.add(
            FilterArea(
                area_id=self.area1.document_id, user_id=global_userids['contributor']
            )
        )
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 2 == len(feed)
        assert self.route.document_id == feed[0]['document']['document_id']
        assert self.waypoint1.document_id == feed[1]['document']['document_id']

    def test_get_feed_areas_filter_ignoring_admin_changes(self):
        """Test that personal feed area filter ignores admin-user changes."""
        import c2corg_api.routers.feed as feed_mod

        feed_mod._feed_admin_user_account_id = global_userids['contributor']
        self.session.add(
            FilterArea(
                area_id=self.area1.document_id, user_id=global_userids['contributor']
            )
        )
        self.session.flush()

        try:
            r = self.client.get(
                '/v2/personal-feed', headers=self._auth_headers('contributor')
            )
            assert r.status_code == 200
            body = r.json()

            feed = body['feed']
            assert 0 == len(feed)
        finally:
            feed_mod._feed_admin_user_account_id = None

    def test_get_feed_areas_and_activities_filter(self):
        """Get personal feed with an area and activity filter."""
        user = self.session.get(User, global_userids['contributor'])
        assert user is not None
        user.feed_filter_activities = ['hiking']
        self.session.add(
            FilterArea(
                area_id=self.area1.document_id, user_id=global_userids['contributor']
            )
        )
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.route.document_id == feed[0]['document']['document_id']

    def test_get_feed_followed_user_filter_ignored(self):
        """Get personal feed with a followed user filter without area and
        activity filter (returns all changes)."""
        self.session.add(
            FollowedUser(
                followed_user_id=global_userids['contributor2'],
                follower_user_id=global_userids['contributor'],
            )
        )
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 4 == len(feed)

    def test_get_feed_followed_user_filter_followed_only(self):
        """Get personal feed with a followed user and `feed_followed_only`."""
        user = self.session.get(User, global_userids['contributor'])
        assert user is not None
        user.feed_followed_only = True

        self.session.add(
            FollowedUser(
                followed_user_id=global_userids['contributor2'],
                follower_user_id=global_userids['contributor'],
            )
        )
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 2 == len(feed)
        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_followed_user_and_activity_filter(self):
        """Get personal feed with a followed user and an activity filter."""
        user = self.session.get(User, global_userids['contributor'])
        assert user is not None
        user.feed_filter_activities = ['hiking']

        self.session.add(
            FollowedUser(
                followed_user_id=global_userids['contributor2'],
                follower_user_id=global_userids['contributor'],
            )
        )
        self.session.flush()

        r = self.client.get(
            '/v2/personal-feed', headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 3 == len(feed)
        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.route.document_id == feed[1]['document']['document_id']
        assert self.waypoint2.document_id == feed[2]['document']['document_id']

    def test_get_feed_areas_filter_paginated(self):
        """Get personal feed with an area filter (paginated)."""
        self.session.add(
            FilterArea(
                area_id=self.area1.document_id, user_id=global_userids['contributor']
            )
        )
        self.session.flush()

        headers = self._auth_headers('contributor')

        # first page
        r = self.client.get('/v2/personal-feed?limit=1', headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.route.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # second page
        r = self.client.get(
            '/v2/personal-feed?limit=1&token=' + pagination_token, headers=headers
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.waypoint1.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # empty response
        r = self.client.get(
            '/v2/personal-feed?limit=1&token=' + pagination_token, headers=headers
        )
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 0 == len(feed)


class TestProfileFeedRouter(BaseFeedTestRouter):
    def test_get_feed_invalid_user_id(self):
        headers = self._auth_headers('contributor')
        r = self.client.get('/v2/profile-feed?u=invalid-user-id', headers=headers)
        assert r.status_code == 400

    def test_get_feed_missing_user_id(self):
        headers = self._auth_headers('contributor')
        r = self.client.get('/v2/profile-feed', headers=headers)
        assert r.status_code == 400

    def test_get_feed_non_existing_user(self):
        headers = self._auth_headers('contributor')
        r = self.client.get('/v2/profile-feed?u=-1', headers=headers)
        assert r.status_code == 404

    def test_get_profile_contributor(self):
        """Get profile feed for 'contributor'."""
        headers = self._auth_headers('contributor')
        user_id = global_userids['contributor']
        r = self.client.get('/v2/profile-feed?u=' + str(user_id), headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 3 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.route.document_id == feed[1]['document']['document_id']
        assert self.waypoint1.document_id == feed[2]['document']['document_id']

    def test_get_profile_contributor2(self):
        """Get profile feed for 'contributor2'."""
        headers = self._auth_headers('contributor')
        user_id = global_userids['contributor2']
        r = self.client.get('/v2/profile-feed?u=' + str(user_id), headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 2 == len(feed)

        assert self.outing.document_id == feed[0]['document']['document_id']
        assert self.waypoint2.document_id == feed[1]['document']['document_id']

    def test_get_feed_unauthenticated_public_profile(self):
        """Get the public profile feed for 'contributor2'."""
        user_id = global_userids['contributor2']
        user = self.session.get(User, user_id)
        assert user is not None
        user.is_profile_public = True
        self.session.flush()

        r = self.client.get('/v2/profile-feed?u=' + str(user_id))
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 2 == len(feed)

    def test_get_feed_unauthenticated_non_public_profile(self):
        """Try to get the non-public profile feed for 'contributor2'."""
        user_id = global_userids['contributor2']
        r = self.client.get('/v2/profile-feed?u=' + str(user_id))
        assert r.status_code == 403

    def test_get_profile_contributor2_paginated(self):
        """Get profile feed for 'contributor2' (paginated)."""
        headers = self._auth_headers('contributor')
        user_id = global_userids['contributor2']
        url = '/v2/profile-feed?u=' + str(user_id) + '&limit=1'
        r = self.client.get(url, headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.outing.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # second page
        url = (
            '/v2/profile-feed?u=' + str(user_id) + '&limit=1&token=' + pagination_token
        )
        r = self.client.get(url, headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 1 == len(feed)
        assert self.waypoint2.document_id == feed[0]['document']['document_id']
        pagination_token = body['pagination_token']

        # empty response
        url = (
            '/v2/profile-feed?u=' + str(user_id) + '&limit=1&token=' + pagination_token
        )
        r = self.client.get(url, headers=headers)
        assert r.status_code == 200
        body = r.json()

        feed = body['feed']
        assert 0 == len(feed)
