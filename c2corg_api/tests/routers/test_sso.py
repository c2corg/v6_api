"""
Tests for the FastAPI SSO routers (``/v2/sso_sync`` and ``/v2/sso_login``).

Mirrors ``c2corg_api/tests/views/test_sso.py``.
"""

from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.routers.sso import configure_sso_router
from c2corg_api.security.discourse_client import (
    DiscourseClientError,
    set_discourse_client,
)
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.views.sso import localized_now, sso_expire_from_now

sso_domain = 'external.domain.net'
sso_key = 'sso_test_key'


class TestSsoSyncRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_sso_router(settings)

        self.contributor = (
            self.session.query(User).filter(User.username == 'contributor').one()
        )

        self.session.add(SsoKey(domain=sso_domain, key=sso_key))
        self.contributor_external_id = SsoExternalId(
            domain=sso_domain, external_id='1', user=self.contributor
        )
        self.session.add(self.contributor_external_id)
        self.session.flush()

        set_discourse_client(None)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        set_discourse_client(None)
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    @staticmethod
    def token_from_url(url):
        qs = parse_qs(urlparse(url).query)
        return qs.get('token')[0]

    def test_no_sso_key(self):
        request_body = {'external_id': '999', 'email': 'newuser@external.domain.net'}
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        # sso_key is a required field on the Pydantic model, so FastAPI's
        # validation error handler returns it at the top-level.
        errors = body.get('errors')
        assert 'sso_key' == errors[0].get('name')
        assert 'Required' == errors[0].get('description')

    def test_bad_sso_key(self):
        request_body = {
            'sso_key': 'bad_sso_key',
            'external_id': '999',
            'email': 'newuser@external.domain.net',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 403
        body = r.json()
        errors = body['errors']
        assert 'sso_key' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_no_external_id(self):
        request_body = {'sso_key': sso_key}
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        errors = body.get('errors')
        assert 'external_id' == errors[0].get('name')
        assert 'Required' == errors[0].get('description')

    def test_new_user_no_email(self):
        request_body = {'sso_key': sso_key, 'external_id': '999'}
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        errors = body['errors']
        assert 'email' == errors[0].get('name')
        assert 'Required' == errors[0].get('description')

    def test_new_user_existing_username(self):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': self.contributor.username,
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        errors = body['errors']
        assert 'already used username' == errors[0].get('description')

    def test_new_user_existing_forum_username(self):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'forum_username': self.contributor.forum_username,
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        errors = body['errors']
        assert 'already used forum_username' == errors[0].get('description')

    def test_new_user_forum_username_too_long(self):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'forum_username': 'more_than_twenty_five_characters',
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 400
        body = r.json()
        errors = body['errors']
        assert 'forum_username' == errors[0].get('name')
        assert 'Longer than maximum length 25' == errors[0].get('description')

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(
                side_effect=DiscourseClientError(response=Mock(status_code=404))
            ),
            sync_sso=Mock(return_value={'id': 555}),
        ),
    )
    def test_new_user_success(self, discourse_mock):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'name': 'New User',
            'forum_username': 'NewUser',
            'lang': 'fr',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200
        body = r.json()

        sso_external_id = (
            self.session.query(SsoExternalId)
            .filter(SsoExternalId.domain == sso_domain)
            .filter(SsoExternalId.external_id == '999')
            .one_or_none()
        )
        assert sso_external_id is not None
        sso_user = sso_external_id.user
        assert 'newuser' == sso_user.username
        assert 'New User' == sso_user.name
        assert 'NewUser' == sso_user.forum_username

        assert sso_external_id.token == self.token_from_url(body.get('url'))

        client = discourse_mock.return_value
        client.by_external_id.assert_called_with(sso_external_id.user.id)
        client.sync_sso.assert_called_once_with(
            sso_secret=settings.get('discourse.sso_secret'),
            name='New User',
            username='NewUser',
            email='newuser@external.domain.net',
            external_id=sso_user.id,
            **{'custom.user_field_1': str(sso_user.id)},
        )

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'})
        ),
    )
    def test_success_by_email(self, discourse_mock):
        request_body = {
            'sso_key': sso_key,
            'external_id': '1',
            'email': self.contributor.email,
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200
        body = r.json()

        sso_external_id = (
            self.session.query(SsoExternalId)
            .filter(SsoExternalId.domain == sso_domain)
            .filter(SsoExternalId.external_id == '1')
            .one_or_none()
        )
        assert sso_external_id is not None
        assert 'contributor' == sso_external_id.user.username

        assert sso_external_id.token == self.token_from_url(body.get('url'))

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'})
        ),
    )
    def test_success_by_external_id(self, discourse_mock):
        request_body = {
            'sso_key': sso_key,
            'external_id': '1',
            'email': 'email@external.domain.net',
            'username': self.contributor.username,
            'name': self.contributor.name,
            'forum_username': self.contributor.forum_username,
            'lang': 'fr',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200
        body = r.json()

        self.session.expire(self.contributor_external_id)
        assert self.contributor_external_id.token == self.token_from_url(
            body.get('url')
        )

        client = discourse_mock.return_value
        client.by_external_id.assert_called_once_with(self.contributor.id)

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(by_external_id=Mock(side_effect=ConnectionError())),
    )
    def test_discourse_down(self, discourse_mock):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'name': 'New User',
            'forum_username': 'NewUser',
            'lang': 'fr',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 500
        body = r.json()
        errors = body['errors']
        assert 'Error with Discourse' == errors[0].get('description')

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(
                side_effect=DiscourseClientError(response=Mock(status_code=404))
            ),
            sync_sso=Mock(return_value={'id': 555}),
        ),
    )
    def test_new_user_no_name(self, discourse_mock):
        """name and forum_username should default to username"""
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'lang': 'fr',
        }
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200

        sso_external_id = (
            self.session.query(SsoExternalId)
            .filter(SsoExternalId.domain == sso_domain)
            .filter(SsoExternalId.external_id == '999')
            .one_or_none()
        )
        assert sso_external_id is not None
        sso_user = sso_external_id.user
        assert 'newuser' == sso_user.username
        assert 'newuser' == sso_user.name
        assert 'newuser' == sso_user.forum_username

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'}),
            sync_sso=Mock(return_value={'id': 1}),
            groups=Mock(return_value=[]),
        ),
    )
    def test_not_found_group(self, discourse_mock):
        request_body = {'sso_key': sso_key, 'external_id': '1', 'group': 'group_1'}
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'}),
            groups=Mock(return_value=[{'id': 222, 'name': 'group_1'}]),
            add_user_to_group=Mock(),
        ),
    )
    def test_existing_group(self, discourse_mock):
        request_body = {'sso_key': sso_key, 'external_id': '1', 'groups': 'group_1'}
        r = self.client.post('/v2/sso_sync', json=request_body)
        assert r.status_code == 200

        client = discourse_mock.return_value
        client.add_user_to_group.assert_called_once_with(222, 1)


class TestSsoLoginRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_sso_router(settings)

        self.contributor = (
            self.session.query(User).filter(User.username == 'contributor').one()
        )

        self.session.add(SsoKey(domain=sso_domain, key=sso_key))

        self.sso_external_id = SsoExternalId(
            domain=sso_domain, external_id='1', user=self.contributor
        )
        self.sso_external_id.token = 'good_token'
        self.session.add(self.sso_external_id)

        self.session.flush()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        set_discourse_client(None)
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def test_no_token(self):
        r = self.client.post('/v2/sso_login', json={})
        assert r.status_code == 400
        body = r.json()
        errors = body.get('errors')
        assert 'token' == errors[0].get('name')
        assert 'Required' == errors[0].get('description')

    def test_invalid_token(self):
        r = self.client.post('/v2/sso_login', json={'token': 'bad_token'})
        assert r.status_code == 403
        body = r.json()
        errors = body['errors']
        assert 'token' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_expired_token(self):
        self.sso_external_id.expire = localized_now()
        self.session.flush()

        r = self.client.post('/v2/sso_login', json={'token': 'good_token'})
        assert r.status_code == 403
        body = r.json()
        errors = body['errors']
        assert 'token' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_success(self):
        self.sso_external_id.expire = sso_expire_from_now()
        self.session.flush()

        r = self.client.post(
            '/v2/sso_login', json={'discourse': True, 'token': 'good_token'}
        )
        assert r.status_code == 200
        body = r.json()
        assert 'token' in body

    @patch(
        'c2corg_api.routers.sso.get_discourse_client',
        return_value=Mock(
            redirect_without_nonce=Mock(return_value='https://discourse_redirect')
        ),
    )
    def test_success_discourse_up(self, discourse_mock):
        self.sso_external_id.expire = sso_expire_from_now()
        self.session.flush()

        r = self.client.post(
            '/v2/sso_login', json={'discourse': True, 'token': 'good_token'}
        )
        assert r.status_code == 200
        body = r.json()
        assert 'token' in body

    @patch(
        'c2corg_api.routers.sso.get_discourse_client',
        return_value=Mock(redirect_without_nonce=Mock(side_effect=Exception)),
    )
    def test_success_discourse_down(self, discourse_mock):
        # SSO login allowed even if Discourse is down.
        self.sso_external_id.expire = sso_expire_from_now()
        self.session.flush()

        r = self.client.post(
            '/v2/sso_login', json={'discourse': True, 'token': 'good_token'}
        )
        assert r.status_code == 200
        body = r.json()
        assert 'token' in body
