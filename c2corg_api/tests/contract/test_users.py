from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.security.roles import hash_token
from c2corg_api.tests.contract import ContractTest, check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT
from c2corg_api.tests.views.test_user import BaseUserTestRest
from c2corg_api.views.sso import sso_expire_from_now

SEND_EMAIL = 'c2corg_api.emails.email_service.EmailService._send_email'

NEW_USER = {
    'username': 'newuser',
    'forum_username': 'newuserf',
    'name': 'New User',
    'password': 'Super$ecret1',  # nosec - test fixture
    'email': 'newuser@camptocamp.org',
}


class UserContractTest(ContractTest, BaseUserTestRest):
    """The user routes, with Discourse faked (see BaseUserTestRest)."""

    @pytest.fixture(autouse=True)
    def _setup_user_contract_test(self, client, _setup_base_user_test_rest):
        self.discourse_client.redirect.return_value = 'https://discourse_redirect'

    def register(self, client, settings):
        """Register NEW_USER, validate the email and return the response."""
        with patch(SEND_EMAIL) as send_email:
            registered = self.post(client, settings, '/users/register', NEW_USER)
            nonce = self.extract_nonce(send_email, 'validate_register_email')
        validated = self.post(
            client, settings, f'/users/validate_register_email/{nonce}', {}
        )
        return registered, validated

    def login(self, client, settings, passwords, username, password, **kwargs):
        body = dict(username=username, password=password, **kwargs)
        return self.post(client, settings, '/users/login', body)


class TestRegisterAndLogin(UserContractTest):
    @contract(
        ('POST', '/users/register'),
        ('POST', '/users/validate_register_email/{nonce}'),
        ('POST', '/users/login'),
        ('POST', '/users/renew'),
        ('POST', '/users/logout'),
    )
    def test_register_login_renew_logout(self, client, settings, passwords):
        registered, validated = self.register(client, settings)
        check_snapshot('users_register', registered)
        check_snapshot('users_validate_register_email', validated)

        login = self.login(
            client, settings, passwords, NEW_USER['username'], NEW_USER['password']
        )
        check_snapshot('users_login', login)
        token = login.json['token']
        auth = {'Authorization': f'JWT token="{token}"'}

        renewed = self.post(client, settings, '/users/renew', {}, headers=dict(auth))
        check_snapshot('users_renew', renewed)
        # the renewal revoked the token of the login
        auth = {'Authorization': f'JWT token="{renewed.json["token"]}"'}
        logout = self.post(client, settings, '/users/logout', {}, headers=dict(auth))
        check_snapshot('users_logout', logout)

    @contract(('POST', '/users/login'))
    def test_login_for_discourse(self, client, settings, passwords):
        response = self.login(
            client,
            settings,
            passwords,
            'contributor',
            passwords['contributor'],
            discourse=True,
        )
        check_snapshot('users_login_discourse', response)
        assert response.json['redirect_internal'] == 'https://discourse_redirect'

    @contract(('POST', '/users/login'))
    def test_login_failure(self, client, settings):
        body = {'username': 'contributor', 'password': 'wrong'}
        check_snapshot(
            'users_login_failure',
            self.post(client, settings, '/users/login', body, status=401),
        )

    @contract(('POST', '/users/discourse-redirect'))
    def test_discourse_redirect(self, client, settings):
        response = self.post(
            client,
            settings,
            '/users/discourse-redirect',
            {'sso': 'x', 'sig': 'y'},
            user='moderator',
        )
        check_snapshot('users_discourse_redirect', response)


class TestPassword(UserContractTest):
    @contract(
        ('POST', '/users/request_password_change'),
        ('POST', '/users/validate_new_password/{nonce}'),
    )
    def test_password_change(self, client, settings):
        with patch(SEND_EMAIL) as send_email:
            requested = self.post(
                client,
                settings,
                '/users/request_password_change',
                {'email': 'contributor@camptocamp.org'},
            )
            nonce = self.extract_nonce(send_email, 'change_password')
        check_snapshot('users_request_password_change', requested)
        validated = self.post(
            client,
            settings,
            f'/users/validate_new_password/{nonce}',
            {'password': 'New$Password1'},  # nosec - test fixture
        )
        check_snapshot('users_validate_new_password', validated)


class TestAccount(UserContractTest):
    @contract(
        ('GET', '/users/account'),
        ('POST', '/users/account'),
        ('POST', '/users/validate_change_email/{nonce}'),
    )
    def test_account_and_email_change(self, client, settings, passwords):
        check_snapshot(
            'users_account',
            self.get(client, settings, '/users/account', user='contributor'),
        )
        body = {
            'currentpassword': passwords['contributor'],
            'email': 'new.address@camptocamp.org',
        }
        with patch(SEND_EMAIL) as send_email:
            changed = self.post(
                client, settings, '/users/account', body, user='contributor'
            )
            nonce = self.extract_nonce(send_email, 'validate_change_email')
        check_snapshot('users_account_update', changed)
        validated = self.post(
            client, settings, f'/users/validate_change_email/{nonce}', {}
        )
        check_snapshot('users_validate_change_email', validated)

    @contract(('POST', '/users/update_preferred_language'))
    def test_preferred_language(self, client, settings):
        response = self.post(
            client,
            settings,
            '/users/update_preferred_language',
            {'lang': 'fr'},
            user='contributor',
        )
        check_snapshot('users_update_preferred_language', response)

    @contract(('GET', '/users/preferences'), ('POST', '/users/preferences'))
    def test_preferences(self, client, settings):
        body = {
            'followed_only': True,
            'activities': ['hiking'],
            'langs': ['fr', 'en'],
            'areas': [],
        }
        posted = self.post(
            client, settings, '/users/preferences', body, user='contributor'
        )
        check_snapshot('users_preferences_update', posted)
        check_snapshot(
            'users_preferences',
            self.get(client, settings, '/users/preferences', user='contributor'),
        )

    @contract(('GET', '/users/mailinglists'), ('POST', '/users/mailinglists'))
    def test_mailinglists(self, client, settings):
        posted = self.post(
            client,
            settings,
            '/users/mailinglists',
            {'meteofrance-74': True},
            user='contributor',
        )
        check_snapshot('users_mailinglists_update', posted)
        check_snapshot(
            'users_mailinglists',
            self.get(client, settings, '/users/mailinglists', user='contributor'),
        )

    @contract(('PUT', '/profiles/{id}'))
    def test_profile_update(self, client, settings, passwords):
        registered, _ = self.register(client, settings)
        user_id = registered.json['id']
        login = self.login(
            client, settings, passwords, NEW_USER['username'], NEW_USER['password']
        )
        auth = {'Authorization': f'JWT token="{login.json["token"]}"'}
        profile = self.get(
            client, settings, f'/profiles/{user_id}', headers=dict(auth)
        ).json
        for field in (
            'areas',
            'available_langs',
            'associations',
            'cooked',
            'name',
            'forum_username',
        ):
            profile.pop(field, None)
        profile['locales'][0]['description'] = 'Hello'
        body = {'message': 'contract test', 'document': profile}
        response = self.put(
            client, settings, f'/profiles/{user_id}', body, headers=dict(auth)
        )
        check_snapshot('profiles_update', response)


class TestFollow(UserContractTest):
    @contract(
        ('POST', '/users/follow'),
        ('GET', '/users/following'),
        ('GET', '/users/following-user/{id}'),
        ('POST', '/users/unfollow'),
    )
    def test_follow_and_unfollow(self, client, settings, user_ids):
        moderator = {'user_id': user_ids['moderator']}
        check_snapshot(
            'users_follow',
            self.post(client, settings, '/users/follow', moderator, user='contributor'),
        )
        check_snapshot(
            'users_following',
            self.get(client, settings, '/users/following', user='contributor'),
        )
        check_snapshot(
            'users_following_user',
            self.get(
                client,
                settings,
                f'/users/following-user/{moderator["user_id"]}',
                user='contributor',
            ),
        )
        check_snapshot(
            'users_unfollow',
            self.post(
                client, settings, '/users/unfollow', moderator, user='contributor'
            ),
        )


class TestBlock(UserContractTest):
    @contract(
        ('POST', '/users/block'),
        ('GET', '/users/blocked'),
        ('GET', '/users/blocked/{id}'),
        ('POST', '/users/unblock'),
    )
    def test_block_and_unblock(self, client, settings, user_ids):
        user_id = user_ids['contributor2']
        body = {'user_id': user_id}
        check_snapshot(
            'users_block',
            self.post(client, settings, '/users/block', body, user='moderator'),
        )
        check_snapshot(
            'users_blocked',
            self.get(client, settings, '/users/blocked', user='moderator'),
        )
        check_snapshot(
            'users_blocked_user',
            self.get(client, settings, f'/users/blocked/{user_id}', user='moderator'),
        )
        check_snapshot(
            'users_unblock',
            self.post(client, settings, '/users/unblock', body, user='moderator'),
        )


# the GET routes of the users, by permission, and whether they are JSON views
USER_READS = [
    ('/users/account', 'authenticated', False),
    ('/users/preferences', 'authenticated', False),
    ('/users/mailinglists', 'authenticated', False),
    ('/users/following', 'authenticated', True),
    ('/users/following-user/{id}', 'authenticated', True),
    ('/users/blocked', 'moderator', True),
    ('/users/blocked/{id}', 'moderator', True),
]


class TestUserReads(UserContractTest):
    def url(self, user_ids, path):
        return path.format(id=user_ids['contributor2'])

    @contract(*[('GET', path) for path, _, _ in USER_READS])
    def test_permissions(self, client, settings, user_ids):
        for path, permission, _ in USER_READS:
            check_snapshot(
                'users_read_anonymous',
                self.get(client, settings, self.url(user_ids, path), status=403),
            )
            if permission == 'moderator':
                response = self.get(
                    client,
                    settings,
                    self.url(user_ids, path),
                    user='contributor',
                    status=403,
                )
                check_snapshot('users_read_not_moderator', response)

    @contract(*[('GET', path) for path, _, json in USER_READS if json])
    def test_content_type(self, client, settings, user_ids):
        headers = {'Content-Type': 'text/plain'}
        for path, _, json in USER_READS:
            if json:
                response = self.get(
                    client,
                    settings,
                    self.url(user_ids, path),
                    user='moderator',
                    headers=headers,
                    status=415,
                )
                check_snapshot('users_read_wrong_content_type', response)

    @contract(('GET', '/users/account'))
    def test_account_is_not_cached(self, client, settings):
        response = self.get(client, settings, '/users/account', user='contributor')
        assert response.headers['Cache-Control'] == (
            'max-age=0, must-revalidate, no-cache, no-store'
        )
        # http_cache=0 of Pyramid
        assert response.headers['Pragma'] == 'no-cache'
        assert 'Expires' in response.headers
        assert 'Last-Modified' in response.headers

    @contract(('GET', '/users/token'))
    def test_token(self, client, settings, user_ids):
        response = self.get(client, settings, '/users/token', user='contributor')
        assert response.json['user'] == user_ids['contributor']
        assert isinstance(response.json['expire'], int)
        assert response.headers['Cache-Control'] == (
            'max-age=0, must-revalidate, no-cache, no-store'
        )

    @contract(('GET', '/users/blocked/{id}'))
    def test_blocked_of_unknown_user(self, client, settings):
        response = self.get(
            client, settings, '/users/blocked/9999999', user='moderator', status=400
        )
        check_snapshot('users_blocked_unknown', response)
        assert response.json['errors'][0]['description'] == 'Unknown user 9999999'

    @contract(('GET', '/users/preferences'))
    def test_preferences_in_a_lang(self, client, settings):
        response = self.get(
            client,
            settings,
            '/users/preferences',
            user='contributor',
            params={'pl': 'fr'},
        )
        check_snapshot('users_preferences_fr', response)


class TestDocumentUserActions(UserContractTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_user_actions(
        self, client, settings, _setup_user_contract_test
    ):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
        }
        waypoint_id = self.post(
            client, settings, '/waypoints', body, user='contributor'
        ).json['document_id']
        self.document_id = waypoint_id
        # only routes can be tagged
        route = {
            'main_waypoint_id': waypoint_id,
            'activities': ['hiking'],
            'locales': [{'lang': 'en', 'title': 'Normal route'}],
            'associations': {'waypoints': [{'document_id': waypoint_id}]},
        }
        self.route_id = self.post(
            client, settings, '/routes', route, user='contributor'
        ).json['document_id']

    @contract(
        ('POST', '/tags/add'),
        ('GET', '/tags/has/{document_id}'),
        ('POST', '/tags/remove'),
    )
    def test_tags(self, client, settings):
        body = {'document_id': self.route_id}
        check_snapshot(
            'tags_add',
            self.post(client, settings, '/tags/add', body, user='contributor'),
        )
        check_snapshot(
            'tags_has',
            self.get(
                client, settings, f'/tags/has/{self.route_id}', user='contributor'
            ),
        )
        check_snapshot(
            'tags_remove',
            self.post(client, settings, '/tags/remove', body, user='contributor'),
        )

    @contract(('GET', '/tags/has/{document_id}'))
    def test_tags_has_needs_a_user(self, client, settings):
        response = self.get(client, settings, f'/tags/has/{self.route_id}', status=403)
        check_snapshot('tags_has_anonymous', response)

    @contract(('GET', '/tags/has/{document_id}'))
    def test_tags_has_content_type(self, client, settings):
        # a JSON view: a Content-Type other than JSON is refused, even before
        # the permission check
        url = f'/tags/has/{self.route_id}'
        for user in (None, 'contributor'):
            response = self.get(
                client,
                settings,
                url,
                user=user,
                headers={'Content-Type': 'text/plain'},
                status=415,
            )
            check_snapshot('tags_has_wrong_content_type', response)
        json_type = {'Content-Type': 'application/json; charset=utf-8'}
        response = self.get(
            client, settings, url, user='contributor', headers=json_type
        )
        assert response.json == {'todo': False}

    @contract(('POST', '/forum/topics'))
    def test_forum_topic(self, client, settings):
        # the real Discourse client, with the HTTP call faked
        self.set_discourse_not_mocked()
        with patch(
            'pydiscourse.client.DiscourseClient.create_post',
            return_value={'topic_id': 10},
        ):
            response = self.post(
                client,
                settings,
                '/forum/topics',
                {'document_id': self.document_id, 'lang': 'en'},
                user='contributor',
            )
        check_snapshot('forum_topics', response)


class TestSso(UserContractTest):
    @pytest.fixture(autouse=True)
    def _setup_test_sso(self, client, session, user_ids, _setup_user_contract_test):
        session.add(
            SsoKey(domain='external.domain.net', key=hash_token('sso_test_key'))
        )
        contributor = session.get(User, user_ids['contributor'])
        self.external_id = SsoExternalId(
            domain='external.domain.net', external_id='1', user=contributor
        )
        session.add(self.external_id)
        session.flush()

    @contract(('POST', '/sso_sync'), ('POST', '/sso_login'))
    def test_sync_then_login(self, client, session, settings):
        synced = self.post(
            client,
            settings,
            '/sso_sync',
            {'sso_key': 'sso_test_key', 'external_id': '1'},
        )
        check_snapshot('sso_sync', synced)
        session.expire(self.external_id)
        self.external_id.expire = sso_expire_from_now()
        session.flush()
        # the token is in the URL answered: the database keeps its hash
        token = parse_qs(urlparse(synced.json['url']).query)['token'][0]
        login = self.post(client, settings, '/sso_login', {'token': token})
        check_snapshot('sso_login', login)
