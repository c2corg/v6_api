"""
Tests for the FastAPI User Mailinglists router
(``/v2/users/mailinglists``).

Mirrors ``c2corg_api/tests/views/test_user_mailinglists.py``.
"""

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.common.attributes import Mailinglists
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class TestUserMailinglistsRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        self.contributor = self.session.get(User, global_userids['contributor'])

        ml1 = Mailinglist(
            listname='meteofrance-74',
            email=self.contributor.email,
            user_id=self.contributor.id,
            user=self.contributor,
        )
        ml2 = Mailinglist(
            listname='avalanche.en',
            email=self.contributor.email,
            user_id=self.contributor.id,
            user=self.contributor,
        )
        self.session.add_all([ml1, ml2])
        self.session.flush()

        self._prefix = '/v2/users/mailinglists'

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

    def test_get_mailinglists_unauthenticated(self):
        r = self.client.get(self._prefix)
        assert r.status_code == 403

    def test_get_mailinglists(self):
        r = self.client.get(self._prefix, headers=self._auth_headers('contributor'))
        assert r.status_code == 200
        body = r.json()

        assert len(body) == len(Mailinglists)
        for ml in Mailinglists:
            assert ml in body
            if ml in ['meteofrance-74', 'avalanche.en']:
                assert body[ml]
            else:
                assert not body[ml]

    def test_post_mailinglists_unauthenticated(self):
        r = self.client.post(self._prefix, json={})
        assert r.status_code == 403

    def test_post_mailinglists_invalid(self):
        request_body = {'wrong_mailinglist_name': True, 'avalanche': 'incorrect_value'}
        r = self.client.post(
            self._prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        body = r.json()
        errors = body['errors']
        assert any('wrong_mailinglist_name' == e.get('name') for e in errors)
        assert any('avalanche' == e.get('name') for e in errors)

    def test_post_mailinglists(self):
        request_body = {'meteofrance-66': True, 'meteofrance-74': False}
        r = self.client.post(
            self._prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        mls = (
            self.session.query(Mailinglist.listname)
            .filter(Mailinglist.email == self.contributor.email)
            .all()
        )
        subscribed = [row[0] for row in mls]
        assert len(subscribed) == 2
        assert 'meteofrance-66' in subscribed
        assert 'avalanche.en' in subscribed
        assert 'meteofrance-74' not in subscribed
