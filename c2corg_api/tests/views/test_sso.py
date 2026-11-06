from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from pydiscourse.exceptions import DiscourseClientError

from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import (
    DisabledDiscourseClient,
    set_discourse_client,
)
from c2corg_api.security.roles import hash_token
from c2corg_api.tests import errors_of, get_json_with_token, send_json
from c2corg_api.views.sso import localized_now, sso_expire_from_now

sso_domain = 'external.domain.net'
sso_key = 'sso_test_key'


class TestSsoSyncRest:
    @pytest.fixture(autouse=True)
    def _setup_test_sso_sync_rest(self, client, session):
        self._url = '/sso_sync'

        self.contributor = (
            session.query(User).filter(User.username == 'contributor').one()
        )

        session.add(
            SsoKey(
                domain=sso_domain,
                key=hash_token(sso_key),
            )
        )
        self.contributor_external_id = SsoExternalId(
            domain=sso_domain,
            external_id='1',
            user=self.contributor,
        )
        session.add(self.contributor_external_id)
        session.flush()

        set_discourse_client(None)

    def test_no_sso_key(self, client):
        request_body = {'external_id': '999', 'email': 'newuser@external.domain.net'}
        body = send_json(client, 'post', self._url, request_body, status=422).json
        errors = errors_of(body)
        assert 'sso_key' == errors[0].get('name')
        assert errors[0].get('description') == 'Field required'

    def test_forum_disabled(self, client, session):
        """Refuse to sync when the API runs without a forum, and create nothing."""
        set_discourse_client(DisabledDiscourseClient())
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'name': 'New User',
            'forum_username': 'NewUser',
            'lang': 'fr',
        }
        body = send_json(client, 'post', self._url, request_body, status=503).json
        assert 'The forum is disabled' == body['errors'][0]['description']
        assert session.query(User).filter(User.username == 'newuser').count() == 0

    def test_bad_sso_key(self, client):
        request_body = {
            'sso_key': 'bad_sso_key',
            'external_id': '999',
            'email': 'newuser@external.domain.net',
        }
        body = send_json(client, 'post', self._url, request_body, status=403).json
        errors = body.get('errors')
        assert 'sso_key' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_the_hash_is_not_a_key(self, client):
        request_body = {'sso_key': hash_token(sso_key), 'external_id': '1'}
        send_json(client, 'post', self._url, request_body, status=403)

    def test_key_stored_as_is(self, client, session):
        # only the hashes are accepted since migration b3d5f8a1c9e2
        session.add(SsoKey(domain='raw.domain.net', key='raw_key'))
        session.add(
            SsoExternalId(
                domain='raw.domain.net', external_id='1', user=self.contributor
            )
        )
        session.flush()

        body = {'sso_key': 'raw_key', 'external_id': '1'}
        send_json(client, 'post', self._url, body, status=403)

    def test_no_external_id(self, client):
        request_body = {'sso_key': sso_key}
        body = send_json(client, 'post', self._url, request_body, status=422).json
        errors = errors_of(body)
        assert 'external_id' == errors[0].get('name')
        assert errors[0].get('description') == 'Field required'

    def test_new_user_no_email(self, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
        }
        body = send_json(client, 'post', self._url, request_body, status=400).json
        errors = body.get('errors')
        assert 'email' == errors[0].get('name')
        assert errors[0].get('description') == 'Required'

    def test_new_user_existing_username(self, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': self.contributor.username,
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        body = send_json(client, 'post', self._url, request_body, status=400).json
        errors = body.get('errors')
        assert 'already used username' == errors[0].get('description')

    def test_new_user_existing_forum_username(self, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'forum_username': self.contributor.forum_username,
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        body = send_json(client, 'post', self._url, request_body, status=400).json
        errors = body.get('errors')
        assert 'already used forum_username' == errors[0].get('description')

    def test_new_user_forum_username_too_long(self, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'forum_username': 'more_than_twenty_five_characters',
            'lang': 'fr',
            'groups': 'group1,group2',
        }
        body = send_json(client, 'post', self._url, request_body, status=400).json
        errors = body.get('errors')
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
    def test_new_user_success(self, discourse_mock, client, session, settings):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'name': 'New User',
            'forum_username': 'NewUser',
            'lang': 'fr',
        }
        body = send_json(client, 'post', self._url, request_body, status=200).json

        sso_external_id = (
            session.query(SsoExternalId)
            .filter(SsoExternalId.domain == sso_domain)
            .filter(SsoExternalId.external_id == '999')
            .one_or_none()
        )
        assert sso_external_id is not None
        sso_user = sso_external_id.user
        assert 'newuser' == sso_user.username
        assert 'New User' == sso_user.name
        assert 'NewUser' == sso_user.forum_username

        assert sso_external_id.token == hash_token(self.token_from_url(body.get('url')))

        discourse = discourse_mock.return_value
        discourse.by_external_id.assert_called_with(sso_external_id.user.id)
        discourse.sync_sso.assert_called_once_with(
            sso_secret=settings.get('discourse.sso_secret'),
            name='New User',
            username='NewUser',
            email='newuser@external.domain.net',
            external_id=sso_user.id,
            **{'custom.user_field_1': str(sso_user.id)},
        )

    def token_from_url(self, url):
        qs = parse_qs(urlparse(url).query)
        return qs.get('token')[0]

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'})
        ),
    )
    def test_success_by_email(self, discourse_mock, client, session):
        request_body = {
            'sso_key': sso_key,
            'external_id': '1',
            'email': self.contributor.email,
        }
        body = send_json(client, 'post', self._url, request_body, status=200).json

        sso_external_id = (
            session.query(SsoExternalId)
            .filter(SsoExternalId.domain == sso_domain)
            .filter(SsoExternalId.external_id == '1')
            .one_or_none()
        )
        assert sso_external_id is not None
        assert 'contributor' == sso_external_id.user.username

        assert sso_external_id.token == hash_token(self.token_from_url(body.get('url')))

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'})
        ),
    )
    def test_success_by_external_id(self, discourse_mock, client, session):
        request_body = {
            'sso_key': sso_key,
            'external_id': '1',
            'email': 'email@external.domain.net',
            'username': self.contributor.username,
            'name': self.contributor.name,
            'forum_username': self.contributor.forum_username,
            'lang': 'fr',
        }
        body = send_json(client, 'post', self._url, request_body, status=200).json

        session.expire(self.contributor_external_id)
        assert self.contributor_external_id.token == hash_token(
            self.token_from_url(body.get('url'))
        )

        discourse = discourse_mock.return_value
        discourse.by_external_id.assert_called_once_with(self.contributor.id)

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(by_external_id=Mock(side_effect=ConnectionError())),
    )
    def test_discourse_down(self, discourse_mock, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'name': 'New User',
            'forum_username': 'NewUser',
            'lang': 'fr',
        }
        body = send_json(client, 'post', self._url, request_body, status=500).json
        errors = body.get('errors')
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
    def test_new_user_no_name(self, discourse_mock, client, session):
        """name and forum_username should default to username"""
        request_body = {
            'sso_key': sso_key,
            'external_id': '999',
            'email': 'newuser@external.domain.net',
            'username': 'newuser',
            'lang': 'fr',
        }
        send_json(client, 'post', self._url, request_body, status=200).json

        sso_external_id = (
            session.query(SsoExternalId)
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
    def test_not_found_group(self, discourse_mock, client):
        request_body = {
            'sso_key': sso_key,
            'external_id': '1',
            'group': 'group_1',
        }
        send_json(client, 'post', self._url, request_body, status=200).json

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient',
        return_value=Mock(
            by_external_id=Mock(return_value={'id': 1, 'username': 'contributor'}),
            groups=Mock(return_value=[{'id': 222, 'name': 'group_1'}]),
            add_user_to_group=Mock(),
        ),
    )
    def test_existing_group(self, discourse_mock, client):
        request_body = {'sso_key': sso_key, 'external_id': '1', 'groups': 'group_1'}
        send_json(client, 'post', self._url, request_body, status=200).json

        discourse = discourse_mock.return_value
        discourse.add_user_to_group.assert_called_once_with(222, 1)


class TestSsoLoginRest:
    @pytest.fixture(autouse=True)
    def _setup_test_sso_login_rest(self, client, session):
        self._url = '/sso_login'

        self.contributor = (
            session.query(User).filter(User.username == 'contributor').one()
        )

        session.add(
            SsoKey(
                domain=sso_domain,
                key=hash_token(sso_key),
            )
        )

        self.sso_external_id = SsoExternalId(
            domain=sso_domain,
            external_id='1',
            user=self.contributor,
        )
        self.sso_external_id.token = hash_token('good_token')
        session.add(self.sso_external_id)

        session.flush()

    def test_no_token(self, client):
        body = send_json(client, 'post', self._url, status=422).json
        errors = errors_of(body)
        assert 'token' == errors[0].get('name')
        assert errors[0].get('description') == 'Field required'

    def test_invalid_token(self, client):
        body = send_json(
            client, 'post', self._url, {'token': 'bad_token'}, status=403
        ).json
        errors = body.get('errors')
        assert 'token' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_expired_token(self, client, session):
        self.sso_external_id.expire = localized_now()
        session.flush()

        body = send_json(
            client, 'post', self._url, params={'token': 'good_token'}, status=403
        ).json
        errors = body.get('errors')
        assert 'token' == errors[0].get('name')
        assert 'Invalid' == errors[0].get('description')

    def test_token_stored_as_is(self, client, session):
        # only the hashes are accepted since migration b3d5f8a1c9e2
        # a test value, not a credential
        self.sso_external_id.token = 'raw_token'  # nosec B105
        self.sso_external_id.expire = sso_expire_from_now()
        session.flush()

        send_json(client, 'post', self._url, {'token': 'raw_token'}, status=403)  # nosec B105

    def test_the_hash_is_not_a_token(self, client, session):
        self.sso_external_id.expire = sso_expire_from_now()
        session.flush()

        send_json(
            client, 'post', self._url, {'token': hash_token('good_token')}, status=403
        )

    def test_success(self, client, session):
        self.sso_external_id.expire = sso_expire_from_now()
        session.flush()

        body = send_json(
            client,
            'post',
            self._url,
            {'discourse': True, 'token': 'good_token'},
            status=200,
        ).json
        assert 'token' in body
        # the API accepts the token of the SSO login
        get_json_with_token(client, '/users/account', body['token'], status=200)
        assert body['id'] == self.contributor.id

    @patch(
        'c2corg_api.views.sso.get_discourse_client',
        return_value=Mock(
            redirect_without_nonce=Mock(return_value='https://discourse_redirect')
        ),
    )
    def test_success_discourse_up(self, discourse_mock, client, session):
        self.sso_external_id.expire = sso_expire_from_now()
        session.flush()

        body = send_json(
            client,
            'post',
            self._url,
            {'discourse': True, 'token': 'good_token'},
            status=200,
        ).json
        assert 'token' in body

    @patch(
        'c2corg_api.views.sso.get_discourse_client',
        return_value=Mock(redirect_without_nonce=Mock(side_effect=Exception)),
    )
    def test_success_discourse_down(self, discourse_mock, client, session):
        # SSO login allowed even if Discourse is down.
        self.sso_external_id.expire = sso_expire_from_now()
        session.flush()

        body = send_json(
            client,
            'post',
            self._url,
            {'discourse': True, 'token': 'good_token'},
            status=200,
        ).json
        assert 'token' in body
