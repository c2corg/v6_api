"""
Tests for the FastAPI document-revert router
(``/v2/documents/revert``).
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.document import DocumentRest


class TestDocumentRevertRouter(BaseTestCase):
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
            elevation=4810,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635957 5723605)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The highest point in Europe',
                )
            ],
        )
        self.session.add(self.waypoint2)
        self.waypoint3 = Waypoint(
            waypoint_type='summit',
            elevation=2432,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635958 5723606)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont de Grange',
                    description='...',
                    summary='Some nice peak',
                )
            ],
        )
        self.session.add(self.waypoint3)
        self.session.flush()

        self.route1 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            main_waypoint_id=self.waypoint2.document_id,
            geometry=DocumentGeometry(
                geom_detail=('SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'),
                geom='SRID=3857;POINT(635961 5723624)',
            ),
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

        DocumentRest.create_new_version(self.waypoint1, contributor_id)
        DocumentRest.create_new_version(self.waypoint2, contributor_id)
        DocumentRest.create_new_version(self.route1, contributor_id)
        update_feed_document_create(self.waypoint1, contributor_id)
        update_feed_document_create(self.waypoint2, contributor_id)
        update_feed_document_create(self.route1, contributor_id)
        self.session.flush()

        assoc = Association.create(
            parent_document=self.waypoint1, child_document=self.route1
        )
        self.session.add(assoc)
        self.session.add(assoc.get_log(contributor_id))
        assoc = Association.create(
            parent_document=self.waypoint2, child_document=self.route1
        )
        self.session.add(assoc)
        self.session.add(assoc.get_log(contributor_id))
        self.session.flush()

        # Change waypoint2
        self.waypoint2.elevation = 8848
        for locale in self.waypoint2.locales:
            if locale.lang == 'en':
                locale.title = 'Mount Everest'
                locale.summary = 'The highest point in the world'
        self.waypoint2.geometry.geom = 'SRID=3857;POINT(0 0)'

        # Change route1
        self.route1.activities = ['skitouring', 'hiking']
        self.route1.elevation_max = 4500
        self.route1.main_waypoint_id = self.waypoint3.document_id
        for locale in self.route1.locales:
            if locale.lang == 'fr':
                locale.title = 'Some new route name'
        self.route1.geometry.geom = 'SRID=3857;POINT(0 0)'
        self.session.flush()

        DocumentRest.update_version(
            self.waypoint2,
            contributor_id,
            'new version',
            [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG],
            ['en'],
        )
        DocumentRest.update_version(
            self.route1,
            contributor_id,
            'new version',
            [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG],
            ['fr'],
        )
        self.session.flush()

        assoc = Association.create(
            parent_document=self.waypoint3, child_document=self.route1
        )
        self.session.add(assoc)
        self.session.add(assoc.get_log(contributor_id))
        self.session.flush()

    def test_revert_unauthorized(self):
        r = self.client.post('/v2/documents/revert', json={})
        assert r.status_code == 403

        r = self.client.post(
            '/v2/documents/revert', json={}, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 403

    def test_revert_invalid_document_id(self):
        body = {'document_id': -1, 'lang': 'en', 'version_id': 123456}
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400

    def test_revert_invalid_version_id(self):
        document_id = self.waypoint2.document_id
        body = {'document_id': document_id, 'lang': 'en', 'version_id': 123456}
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            'Unknown version {}/en/123456'.format(document_id)
            in e.get('description', '')
            for e in errors
        )

    def test_revert_latest_version_id(self):
        document_id = self.waypoint2.document_id
        (version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang == 'en')
            .order_by(DocumentVersion.id.desc())
            .first()
        )

        body = {'document_id': document_id, 'lang': 'en', 'version_id': version_id}
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any('already the latest one' in e.get('description', '') for e in errors)

    def test_revert_waypoint(self):
        document_id = self.waypoint2.document_id
        # Get first version id
        (version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang == 'en')
            .order_by(DocumentVersion.id.asc())
            .first()
        )

        initial_count = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang == 'en')
            .count()
        )

        body = {'document_id': document_id, 'lang': 'en', 'version_id': version_id}
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200

        self.session.expire_all()

        # check a new version was created
        count = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .filter(DocumentVersion.lang == 'en')
            .count()
        )
        assert count == initial_count + 1

        # check the waypoint was reverted
        wp = self.session.get(Waypoint, document_id)
        assert wp is not None
        self.session.refresh(wp)
        assert wp.elevation == 4810

    def test_revert_route(self):
        route_id = self.route1.document_id
        route_lang = 'fr'

        # Get the first version id of the route
        (route_version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(DocumentVersion.document_id == route_id)
            .filter(DocumentVersion.lang == route_lang)
            .order_by(DocumentVersion.id.asc())
            .first()
        )

        body = {
            'document_id': route_id,
            'lang': route_lang,
            'version_id': route_version_id,
        }
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200

        self.session.expire_all()

        # Check the route was reverted to its original state
        route = self.session.get(Route, route_id)
        assert route is not None
        self.session.refresh(route)
        assert route.elevation_max == 1500
        assert route.activities == ['skitouring']
        for locale in route.locales:
            if locale.lang == route_lang:
                assert locale.title == 'Mont Blanc du ciel'
                # title_prefix comes from the current main waypoint;
                # after revert, main_waypoint is still waypoint2 (which
                # was changed to 'Mount Everest')
                assert locale.title_prefix == 'Mount Everest'

        # Now revert waypoint2 to its first version so that the
        # title_prefix of the route should be updated to 'Mont Blanc'.
        waypoint_id = self.waypoint2.document_id
        waypoint_lang = 'en'
        (waypoint_version_id,) = (
            self.session.query(DocumentVersion.id)
            .filter(DocumentVersion.document_id == waypoint_id)
            .filter(DocumentVersion.lang == waypoint_lang)
            .order_by(DocumentVersion.id.asc())
            .first()
        )

        body = {
            'document_id': waypoint_id,
            'lang': waypoint_lang,
            'version_id': waypoint_version_id,
        }
        r = self.client.post(
            '/v2/documents/revert', json=body, headers=self._auth_headers('moderator')
        )
        assert r.status_code == 200

        self.session.expire_all()

        route = self.session.get(Route, route_id)
        assert route is not None
        self.session.refresh(route)
        for locale in route.locales:
            if locale.lang == route_lang:
                assert locale.title == 'Mont Blanc du ciel'
                assert locale.title_prefix == 'Mont Blanc'
