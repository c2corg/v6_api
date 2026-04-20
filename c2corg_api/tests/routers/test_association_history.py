"""
Tests for the FastAPI association-history router
(``/v2/associations-history``).

Exercises the same scenarios as the Pyramid association-history view.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class TestAssociationHistoryFastAPIRouter(BaseTestCase):
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

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[DocumentLocale(lang='en', title='Summit 1')],
        )
        self.waypoint2 = Waypoint(
            waypoint_type='summit',
            elevation=200,
            locales=[DocumentLocale(lang='en', title='Summit 2')],
        )
        self.route1 = Route(
            activities=['skitouring'],
            locales=[DocumentLocale(lang='en', title='Route 1')],
        )

        self.session.add_all([self.waypoint1, self.waypoint2, self.route1])
        self.session.flush()

        # Create some associations and log entries
        assoc1 = Association(
            parent_document_id=self.waypoint1.document_id,
            parent_document_type=self.waypoint1.type,
            child_document_id=self.route1.document_id,
            child_document_type=self.route1.type,
        )
        self.session.add(assoc1)
        self.session.add(assoc1.get_log(user_id, is_creation=True))

        assoc2 = Association(
            parent_document_id=self.waypoint2.document_id,
            parent_document_type=self.waypoint2.type,
            child_document_id=self.route1.document_id,
            child_document_type=self.route1.type,
        )
        self.session.add(assoc2)
        self.session.add(assoc2.get_log(user_id, is_creation=True))

        self.session.flush()

    def test_get_history_no_filter(self):
        r = self.client.get('/v2/associations-history')
        assert r.status_code == 200
        body = r.json()
        assert 'count' in body
        assert 'associations' in body
        assert body['count'] >= 2

    def test_get_history_filter_by_document(self):
        r = self.client.get(f'/v2/associations-history?d={self.route1.document_id}')
        assert r.status_code == 200
        body = r.json()
        assert body['count'] == 2

        for log_entry in body['associations']:
            assert log_entry['written_at'] is not None
            assert isinstance(log_entry['is_creation'], bool)

            user = log_entry['user']
            assert isinstance(user['user_id'], int)
            assert isinstance(user['name'], str)

            child = log_entry['child_document']
            parent = log_entry['parent_document']
            assert (
                child['document_id'] == self.route1.document_id
                or parent['document_id'] == self.route1.document_id
            )

    def test_get_history_filter_by_user(self):
        user_id = global_userids['contributor']
        r = self.client.get(f'/v2/associations-history?u={user_id}')
        assert r.status_code == 200
        body = r.json()
        assert body['count'] >= 2

        for log_entry in body['associations']:
            assert log_entry['user']['user_id'] == user_id

    def test_get_history_filter_by_document_and_user(self):
        user_id = global_userids['contributor']
        r = self.client.get(
            f'/v2/associations-history?d={self.waypoint1.document_id}&u={user_id}'
        )
        assert r.status_code == 200
        body = r.json()
        assert body['count'] == 1

    def test_get_history_pagination(self):
        r = self.client.get(
            f'/v2/associations-history?d={self.route1.document_id}&offset=0&limit=1'
        )
        assert r.status_code == 200
        body = r.json()
        assert body['count'] == 2
        assert len(body['associations']) == 1

    def test_get_history_empty(self):
        r = self.client.get('/v2/associations-history?d=999999')
        assert r.status_code == 200
        body = r.json()
        assert body['count'] == 0
        assert len(body['associations']) == 0

    def test_association_log_structure(self):
        r = self.client.get(f'/v2/associations-history?d={self.route1.document_id}')
        assert r.status_code == 200
        body = r.json()

        log_entry = body['associations'][0]
        assert 'written_at' in log_entry
        assert 'is_creation' in log_entry

        user = log_entry['user']
        assert 'user_id' in user
        assert 'name' in user
        assert 'forum_username' in user
        assert 'robot' in user
        assert 'moderator' in user
        assert 'blocked' in user

        for doc_key in ('child_document', 'parent_document'):
            doc = log_entry[doc_key]
            assert 'document_id' in doc
            assert 'type' in doc
            assert 'locales' in doc
