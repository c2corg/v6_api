"""
Tests for the FastAPI document-tag router
(``/v2/tags/add``, ``/v2/tags/remove``, ``/v2/tags/has/{document_id}``).
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


def has_tagged(session, user_id, document_id):
    return (
        session.query(DocumentTag)
        .filter(DocumentTag.user_id == user_id)
        .filter(DocumentTag.document_id == document_id)
        .first()
        is not None
    )


class BaseDocumentTagTest(BaseTestCase):
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
        self.contributor = self.session.get(User, global_userids['contributor'])
        self.contributor2 = self.session.get(User, global_userids['contributor2'])

        self.route1 = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route1')]
        )
        self.session.add(self.route1)
        self.route2 = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route2')]
        )
        self.session.add(self.route2)
        self.route3 = Route(
            activities=['hiking'], locales=[RouteLocale(lang='en', title='Route3')]
        )
        self.session.add(self.route3)
        self.session.flush()

        self.session.add(
            DocumentTag(
                user_id=self.contributor2.id,
                document_id=self.route2.document_id,
                document_type=ROUTE_TYPE,
            )
        )
        self.session.flush()


class TestDocumentTagRouter(BaseDocumentTagTest):
    def test_tag_unauthenticated(self):
        r = self.client.post('/v2/tags/add', json={})
        assert r.status_code == 403

    def test_tag(self):
        body = {'document_id': self.route1.document_id}

        r = self.client.post(
            '/v2/tags/add', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        self.session.expire_all()
        assert has_tagged(self.session, self.contributor.id, self.route1.document_id)

        log = (
            self.session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == self.route1.document_id)
            .filter(DocumentTagLog.user_id == self.contributor.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert log.is_creation

        # tagging again should fail
        r = self.client.post(
            '/v2/tags/add', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400


class TestDocumentUntagRouter(BaseDocumentTagTest):
    def test_untag_unauthenticated(self):
        r = self.client.post('/v2/tags/remove', json={})
        assert r.status_code == 403

    def test_untag(self):
        body = {'document_id': self.route2.document_id}

        assert has_tagged(self.session, self.contributor2.id, self.route2.document_id)

        r = self.client.post(
            '/v2/tags/remove', json=body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 200

        self.session.expire_all()
        assert not has_tagged(
            self.session, self.contributor2.id, self.route2.document_id
        )

        # removing again should fail
        r = self.client.post(
            '/v2/tags/remove', json=body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400

        log = (
            self.session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == self.route2.document_id)
            .filter(DocumentTagLog.user_id == self.contributor2.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert not log.is_creation

    def test_untag_not_tagged(self):
        body = {'document_id': self.route1.document_id}

        assert not has_tagged(
            self.session, self.contributor.id, self.route1.document_id
        )

        r = self.client.post(
            '/v2/tags/remove', json=body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400

        assert not has_tagged(
            self.session, self.contributor.id, self.route1.document_id
        )


class TestDocumentTaggedRouter(BaseDocumentTagTest):
    def test_has_tagged_unauthenticated(self):
        r = self.client.get('/v2/tags/has/123')
        assert r.status_code == 403

    def test_has_tagged(self):
        r = self.client.get(
            '/v2/tags/has/{}'.format(self.route2.document_id),
            headers=self._auth_headers('contributor2'),
        )
        assert r.status_code == 200
        assert r.json()['todo']

    def test_has_tagged_not(self):
        r = self.client.get(
            '/v2/tags/has/{}'.format(self.route1.document_id),
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 200
        assert not r.json()['todo']
