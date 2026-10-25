from unittest.mock import patch

from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
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

    def setUp(self):
        super().setUp()
        self.discourse_client.redirect.return_value = 'https://discourse_redirect'

    def register(self):
        """Register NEW_USER, validate the email and return the response."""
        with patch(SEND_EMAIL) as send_email:
            registered = self.post('/users/register', NEW_USER)
            nonce = self.extract_nonce(send_email, 'validate_register_email')
        validated = self.post(f'/users/validate_register_email/{nonce}', {})
        return registered, validated

    def login(self, username, password, **kwargs):
        body = dict(username=username, password=password, **kwargs)
        return self.post('/users/login', body)


class TestRegisterAndLogin(UserContractTest):
    @contract(
        ('POST', '/users/register'),
        ('POST', '/users/validate_register_email/{nonce}'),
        ('POST', '/users/login'),
        ('POST', '/users/renew'),
        ('POST', '/users/logout'),
    )
    def test_register_login_renew_logout(self):
        registered, validated = self.register()
        check_snapshot('users_register', registered)
        check_snapshot('users_validate_register_email', validated)

        login = self.login(NEW_USER['username'], NEW_USER['password'])
        check_snapshot('users_login', login)
        token = login.json['token']
        auth = {'Authorization': f'JWT token="{token}"'}

        renewed = self.post('/users/renew', {}, headers=dict(auth))
        check_snapshot('users_renew', renewed)
        logout = self.post('/users/logout', {}, headers=dict(auth))
        check_snapshot('users_logout', logout)

    @contract(('POST', '/users/login'))
    def test_login_for_discourse(self):
        response = self.login(
            'contributor', self.global_passwords['contributor'], discourse=True
        )
        check_snapshot('users_login_discourse', response)
        assert response.json['redirect_internal'] == 'https://discourse_redirect'

    @contract(('POST', '/users/login'))
    def test_login_failure(self):
        body = {'username': 'contributor', 'password': 'wrong'}
        check_snapshot(
            'users_login_failure', self.post('/users/login', body, status=401)
        )

    @contract(('POST', '/users/discourse-redirect'))
    def test_discourse_redirect(self):
        response = self.post(
            '/users/discourse-redirect', {'sso': 'x', 'sig': 'y'}, user='moderator'
        )
        check_snapshot('users_discourse_redirect', response)


class TestPassword(UserContractTest):
    @contract(
        ('POST', '/users/request_password_change'),
        ('POST', '/users/validate_new_password/{nonce}'),
    )
    def test_password_change(self):
        with patch(SEND_EMAIL) as send_email:
            requested = self.post(
                '/users/request_password_change',
                {'email': 'contributor@camptocamp.org'},
            )
            nonce = self.extract_nonce(send_email, 'change_password')
        check_snapshot('users_request_password_change', requested)
        validated = self.post(
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
    def test_account_and_email_change(self):
        check_snapshot('users_account', self.get('/users/account', user='contributor'))
        body = {
            'currentpassword': self.global_passwords['contributor'],
            'email': 'new.address@camptocamp.org',
        }
        with patch(SEND_EMAIL) as send_email:
            changed = self.post('/users/account', body, user='contributor')
            nonce = self.extract_nonce(send_email, 'validate_change_email')
        check_snapshot('users_account_update', changed)
        validated = self.post(f'/users/validate_change_email/{nonce}', {})
        check_snapshot('users_validate_change_email', validated)

    @contract(('POST', '/users/update_preferred_language'))
    def test_preferred_language(self):
        response = self.post(
            '/users/update_preferred_language', {'lang': 'fr'}, user='contributor'
        )
        check_snapshot('users_update_preferred_language', response)

    @contract(('GET', '/users/preferences'), ('POST', '/users/preferences'))
    def test_preferences(self):
        body = {
            'followed_only': True,
            'activities': ['hiking'],
            'langs': ['fr', 'en'],
            'areas': [],
        }
        posted = self.post('/users/preferences', body, user='contributor')
        check_snapshot('users_preferences_update', posted)
        check_snapshot(
            'users_preferences', self.get('/users/preferences', user='contributor')
        )

    @contract(('GET', '/users/mailinglists'), ('POST', '/users/mailinglists'))
    def test_mailinglists(self):
        posted = self.post(
            '/users/mailinglists', {'meteofrance-74': True}, user='contributor'
        )
        check_snapshot('users_mailinglists_update', posted)
        check_snapshot(
            'users_mailinglists', self.get('/users/mailinglists', user='contributor')
        )

    @contract(('PUT', '/profiles/{id}'))
    def test_profile_update(self):
        registered, _ = self.register()
        user_id = registered.json['id']
        login = self.login(NEW_USER['username'], NEW_USER['password'])
        auth = {'Authorization': f'JWT token="{login.json["token"]}"'}
        profile = self.get(f'/profiles/{user_id}', headers=dict(auth)).json
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
        response = self.put(f'/profiles/{user_id}', body, headers=dict(auth))
        check_snapshot('profiles_update', response)


class TestFollow(UserContractTest):
    @contract(
        ('POST', '/users/follow'),
        ('GET', '/users/following'),
        ('GET', '/users/following-user/{id}'),
        ('POST', '/users/unfollow'),
    )
    def test_follow_and_unfollow(self):
        moderator = {'user_id': self.global_userids['moderator']}
        check_snapshot(
            'users_follow', self.post('/users/follow', moderator, user='contributor')
        )
        check_snapshot(
            'users_following', self.get('/users/following', user='contributor')
        )
        check_snapshot(
            'users_following_user',
            self.get(
                f'/users/following-user/{moderator["user_id"]}', user='contributor'
            ),
        )
        check_snapshot(
            'users_unfollow',
            self.post('/users/unfollow', moderator, user='contributor'),
        )


class TestBlock(UserContractTest):
    @contract(
        ('POST', '/users/block'),
        ('GET', '/users/blocked'),
        ('GET', '/users/blocked/{id}'),
        ('POST', '/users/unblock'),
    )
    def test_block_and_unblock(self):
        user_id = self.global_userids['contributor2']
        body = {'user_id': user_id}
        check_snapshot('users_block', self.post('/users/block', body, user='moderator'))
        check_snapshot('users_blocked', self.get('/users/blocked', user='moderator'))
        check_snapshot(
            'users_blocked_user',
            self.get(f'/users/blocked/{user_id}', user='moderator'),
        )
        check_snapshot(
            'users_unblock', self.post('/users/unblock', body, user='moderator')
        )


class TestDocumentUserActions(UserContractTest):
    def setUp(self):
        super().setUp()
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
        }
        waypoint_id = self.post('/waypoints', body, user='contributor').json[
            'document_id'
        ]
        self.document_id = waypoint_id
        # only routes can be tagged
        route = {
            'main_waypoint_id': waypoint_id,
            'activities': ['hiking'],
            'locales': [{'lang': 'en', 'title': 'Normal route'}],
            'associations': {'waypoints': [{'document_id': waypoint_id}]},
        }
        self.route_id = self.post('/routes', route, user='contributor').json[
            'document_id'
        ]

    @contract(
        ('POST', '/tags/add'),
        ('GET', '/tags/has/{document_id}'),
        ('POST', '/tags/remove'),
    )
    def test_tags(self):
        body = {'document_id': self.route_id}
        check_snapshot('tags_add', self.post('/tags/add', body, user='contributor'))
        check_snapshot(
            'tags_has', self.get(f'/tags/has/{self.route_id}', user='contributor')
        )
        check_snapshot(
            'tags_remove', self.post('/tags/remove', body, user='contributor')
        )

    @contract(('POST', '/forum/topics'))
    def test_forum_topic(self):
        # the real Discourse client, with the HTTP call faked
        self.set_discourse_not_mocked()
        with patch(
            'pydiscourse.client.DiscourseClient.create_post',
            return_value={'topic_id': 10},
        ):
            response = self.post(
                '/forum/topics',
                {'document_id': self.document_id, 'lang': 'en'},
                user='contributor',
            )
        check_snapshot('forum_topics', response)


class TestSso(UserContractTest):
    def setUp(self):
        super().setUp()
        self.session.add(SsoKey(domain='external.domain.net', key='sso_test_key'))
        contributor = self.session.get(User, self.global_userids['contributor'])
        self.external_id = SsoExternalId(
            domain='external.domain.net', external_id='1', user=contributor
        )
        self.session.add(self.external_id)
        self.session.flush()

    @contract(('POST', '/sso_sync'), ('POST', '/sso_login'))
    def test_sync_then_login(self):
        synced = self.post('/sso_sync', {'sso_key': 'sso_test_key', 'external_id': '1'})
        check_snapshot('sso_sync', synced)
        self.session.expire(self.external_id)
        self.external_id.expire = sso_expire_from_now()
        self.session.flush()
        login = self.post('/sso_login', {'token': self.external_id.token})
        check_snapshot('sso_login', login)
