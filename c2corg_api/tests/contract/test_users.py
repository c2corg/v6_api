from dataclasses import dataclass
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.security.roles import hash_token
from c2corg_api.tests import extract_nonce
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT
from c2corg_api.views.sso import sso_expire_from_now

SEND_EMAIL = 'c2corg_api.emails.email_service.EmailService._send_email'

NEW_USER = {
    'username': 'newuser',
    'forum_username': 'newuserf',
    'name': 'New User',
    'password': 'Super$ecret1',  # nosec - test fixture
    'email': 'newuser@camptocamp.org',
}


def register(browser):
    """Register NEW_USER, validate the email and return the responses."""
    with patch(SEND_EMAIL) as send_email:
        registered = browser.post('/users/register', NEW_USER)
        nonce = extract_nonce(send_email, 'validate_register_email')
    validated = browser.post(f'/users/validate_register_email/{nonce}', {})
    return registered, validated


def log_in(browser, username, password, **kwargs):
    """Log in through the API; return the response."""
    body = dict(username=username, password=password, **kwargs)
    return browser.post('/users/login', body)


@pytest.mark.usefixtures('discourse')
class TestRegisterAndLogin:
    @contract(
        ('POST', '/users/register'),
        ('POST', '/users/validate_register_email/{nonce}'),
        ('POST', '/users/login'),
        ('POST', '/users/renew'),
        ('POST', '/users/logout'),
    )
    def test_register_login_renew_logout(self, passwords, browser):
        registered, validated = register(browser)
        check_snapshot('users_register', registered)
        check_snapshot('users_validate_register_email', validated)

        login = log_in(browser, NEW_USER['username'], NEW_USER['password'])
        check_snapshot('users_login', login)
        token = login.json['token']
        auth = {'Authorization': f'JWT token="{token}"'}

        renewed = browser.post('/users/renew', {}, headers=dict(auth))
        check_snapshot('users_renew', renewed)
        # the renewal revoked the token of the login
        auth = {'Authorization': f'JWT token="{renewed.json["token"]}"'}
        logout = browser.post('/users/logout', {}, headers=dict(auth))
        check_snapshot('users_logout', logout)

    @contract(('POST', '/users/login'))
    def test_login_for_discourse(self, passwords, browser, discourse):
        response = log_in(
            browser,
            'contributor',
            passwords['contributor'],
            discourse=True,
        )
        check_snapshot('users_login_discourse', response)
        assert response.json['redirect_internal'] == 'https://discourse_redirect'

    @contract(('POST', '/users/login'))
    def test_login_failure(self, browser):
        body = {'username': 'contributor', 'password': 'wrong'}
        check_snapshot(
            'users_login_failure',
            browser.post('/users/login', body, status=401),
        )

    @contract(('POST', '/users/discourse-redirect'))
    def test_discourse_redirect(self, browser):
        response = browser.post(
            '/users/discourse-redirect',
            {'sso': 'x', 'sig': 'y'},
            user='moderator',
        )
        check_snapshot('users_discourse_redirect', response)


@pytest.mark.usefixtures('discourse')
class TestPassword:
    @contract(
        ('POST', '/users/request_password_change'),
        ('POST', '/users/validate_new_password/{nonce}'),
    )
    def test_password_change(self, browser):
        with patch(SEND_EMAIL) as send_email:
            requested = browser.post(
                '/users/request_password_change',
                {'email': 'contributor@camptocamp.org'},
            )
            nonce = extract_nonce(send_email, 'change_password')
        check_snapshot('users_request_password_change', requested)
        validated = browser.post(
            f'/users/validate_new_password/{nonce}',
            {'password': 'New$Password1'},  # nosec - test fixture
        )
        check_snapshot('users_validate_new_password', validated)


@pytest.mark.usefixtures('discourse')
class TestAccount:
    @contract(
        ('GET', '/users/account'),
        ('POST', '/users/account'),
        ('POST', '/users/validate_change_email/{nonce}'),
    )
    def test_account_and_email_change(self, passwords, browser):
        check_snapshot(
            'users_account',
            browser.get('/users/account', user='contributor'),
        )
        body = {
            'currentpassword': passwords['contributor'],
            'email': 'new.address@camptocamp.org',
        }
        with patch(SEND_EMAIL) as send_email:
            changed = browser.post('/users/account', body, user='contributor')
            nonce = extract_nonce(send_email, 'validate_change_email')
        check_snapshot('users_account_update', changed)
        validated = browser.post(f'/users/validate_change_email/{nonce}', {})
        check_snapshot('users_validate_change_email', validated)

    @contract(('POST', '/users/update_preferred_language'))
    def test_preferred_language(self, browser):
        response = browser.post(
            '/users/update_preferred_language',
            {'lang': 'fr'},
            user='contributor',
        )
        check_snapshot('users_update_preferred_language', response)

    @contract(('GET', '/users/preferences'), ('POST', '/users/preferences'))
    def test_preferences(self, browser):
        body = {
            'followed_only': True,
            'activities': ['hiking'],
            'langs': ['fr', 'en'],
            'areas': [],
        }
        posted = browser.post('/users/preferences', body, user='contributor')
        check_snapshot('users_preferences_update', posted)
        check_snapshot(
            'users_preferences',
            browser.get('/users/preferences', user='contributor'),
        )

    @contract(('GET', '/users/mailinglists'), ('POST', '/users/mailinglists'))
    def test_mailinglists(self, browser):
        posted = browser.post(
            '/users/mailinglists',
            {'meteofrance-74': True},
            user='contributor',
        )
        check_snapshot('users_mailinglists_update', posted)
        check_snapshot(
            'users_mailinglists',
            browser.get('/users/mailinglists', user='contributor'),
        )

    @contract(('PUT', '/profiles/{id}'))
    def test_profile_update(self, passwords, browser):
        registered, _ = register(browser)
        user_id = registered.json['id']
        login = log_in(browser, NEW_USER['username'], NEW_USER['password'])
        auth = {'Authorization': f'JWT token="{login.json["token"]}"'}
        profile = browser.get(f'/profiles/{user_id}', headers=dict(auth)).json
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
        response = browser.put(f'/profiles/{user_id}', body, headers=dict(auth))
        check_snapshot('profiles_update', response)


@pytest.mark.usefixtures('discourse')
class TestFollow:
    @contract(
        ('POST', '/users/follow'),
        ('GET', '/users/following'),
        ('GET', '/users/following-user/{id}'),
        ('POST', '/users/unfollow'),
    )
    def test_follow_and_unfollow(self, user_ids, browser):
        moderator = {'user_id': user_ids['moderator']}
        check_snapshot(
            'users_follow',
            browser.post('/users/follow', moderator, user='contributor'),
        )
        check_snapshot(
            'users_following',
            browser.get('/users/following', user='contributor'),
        )
        check_snapshot(
            'users_following_user',
            browser.get(
                f'/users/following-user/{moderator["user_id"]}',
                user='contributor',
            ),
        )
        check_snapshot(
            'users_unfollow',
            browser.post('/users/unfollow', moderator, user='contributor'),
        )


@pytest.mark.usefixtures('discourse')
class TestBlock:
    @contract(
        ('POST', '/users/block'),
        ('GET', '/users/blocked'),
        ('GET', '/users/blocked/{id}'),
        ('POST', '/users/unblock'),
    )
    def test_block_and_unblock(self, user_ids, browser):
        user_id = user_ids['contributor2']
        body = {'user_id': user_id}
        check_snapshot(
            'users_block',
            browser.post('/users/block', body, user='moderator'),
        )
        check_snapshot(
            'users_blocked',
            browser.get('/users/blocked', user='moderator'),
        )
        check_snapshot(
            'users_blocked_user',
            browser.get(f'/users/blocked/{user_id}', user='moderator'),
        )
        check_snapshot(
            'users_unblock',
            browser.post('/users/unblock', body, user='moderator'),
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


def user_url(user_ids, path):
    """The path of a user read, for contributor2."""
    return path.format(id=user_ids['contributor2'])


@pytest.mark.usefixtures('discourse')
class TestUserReads:
    @contract(*[('GET', path) for path, _, _ in USER_READS])
    def test_permissions(self, browser, user_ids):
        for path, permission, _ in USER_READS:
            check_snapshot(
                'users_read_anonymous',
                browser.get(user_url(user_ids, path), status=403),
            )
            if permission == 'moderator':
                response = browser.get(
                    user_url(user_ids, path),
                    user='contributor',
                    status=403,
                )
                check_snapshot('users_read_not_moderator', response)

    @contract(*[('GET', path) for path, _, json in USER_READS if json])
    def test_content_type(self, browser, user_ids):
        headers = {'Content-Type': 'text/plain'}
        for path, _, json in USER_READS:
            if json:
                response = browser.get(
                    user_url(user_ids, path),
                    user='moderator',
                    headers=headers,
                    status=415,
                )
                check_snapshot('users_read_wrong_content_type', response)

    @contract(('GET', '/users/account'))
    def test_account_is_not_cached(self, browser):
        response = browser.get('/users/account', user='contributor')
        assert response.headers['Cache-Control'] == (
            'max-age=0, must-revalidate, no-cache, no-store'
        )
        # http_cache=0 of Pyramid
        assert response.headers['Pragma'] == 'no-cache'
        assert 'Expires' in response.headers
        assert 'Last-Modified' in response.headers

    @contract(('GET', '/users/token'))
    def test_token(self, user_ids, browser):
        response = browser.get('/users/token', user='contributor')
        assert response.json['user'] == user_ids['contributor']
        assert isinstance(response.json['expire'], int)
        assert response.headers['Cache-Control'] == (
            'max-age=0, must-revalidate, no-cache, no-store'
        )

    @contract(('GET', '/users/blocked/{id}'))
    def test_blocked_of_unknown_user(self, browser):
        response = browser.get('/users/blocked/9999999', user='moderator', status=400)
        check_snapshot('users_blocked_unknown', response)
        assert response.json['errors'][0]['description'] == 'Unknown user 9999999'

    @contract(('GET', '/users/preferences'))
    def test_preferences_in_a_lang(self, browser):
        response = browser.get(
            '/users/preferences',
            user='contributor',
            params={'pl': 'fr'},
        )
        check_snapshot('users_preferences_fr', response)


@dataclass
class TaggableDocs:
    """A waypoint and a route on it, which a user can tag."""

    waypoint_id: int
    route_id: int


@pytest.fixture
def taggable(browser) -> TaggableDocs:
    """Create a waypoint and a route on it through the API."""
    body = {
        'waypoint_type': 'summit',
        'elevation': 3779,
        'geometry': {'geom': POINT},
        'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
    }
    waypoint_id = browser.post('/waypoints', body, user='contributor').json[
        'document_id'
    ]
    # only routes can be tagged
    route = {
        'main_waypoint_id': waypoint_id,
        'activities': ['hiking'],
        'locales': [{'lang': 'en', 'title': 'Normal route'}],
        'associations': {'waypoints': [{'document_id': waypoint_id}]},
    }
    route_id = browser.post('/routes', route, user='contributor').json['document_id']
    return TaggableDocs(waypoint_id, route_id)


@pytest.mark.usefixtures('discourse')
class TestDocumentUserActions:
    @contract(
        ('POST', '/tags/add'),
        ('GET', '/tags/has/{document_id}'),
        ('POST', '/tags/remove'),
    )
    def test_tags(self, browser, taggable):
        body = {'document_id': taggable.route_id}
        check_snapshot(
            'tags_add',
            browser.post('/tags/add', body, user='contributor'),
        )
        check_snapshot(
            'tags_has',
            browser.get(f'/tags/has/{taggable.route_id}', user='contributor'),
        )
        check_snapshot(
            'tags_remove',
            browser.post('/tags/remove', body, user='contributor'),
        )

    @contract(('GET', '/tags/has/{document_id}'))
    def test_tags_has_needs_a_user(self, browser, taggable):
        response = browser.get(f'/tags/has/{taggable.route_id}', status=403)
        check_snapshot('tags_has_anonymous', response)

    @contract(('GET', '/tags/has/{document_id}'))
    def test_tags_has_content_type(self, browser, taggable):
        # a JSON view: a Content-Type other than JSON is refused, even before
        # the permission check
        url = f'/tags/has/{taggable.route_id}'
        for user in (None, 'contributor'):
            response = browser.get(
                url,
                user=user,
                headers={'Content-Type': 'text/plain'},
                status=415,
            )
            check_snapshot('tags_has_wrong_content_type', response)
        json_type = {'Content-Type': 'application/json; charset=utf-8'}
        response = browser.get(url, user='contributor', headers=json_type)
        assert response.json == {'todo': False}

    @contract(('POST', '/forum/topics'))
    def test_forum_topic(self, browser, discourse, taggable):
        # the real Discourse client, with the HTTP call faked
        discourse.restore()
        with patch(
            'pydiscourse.client.DiscourseClient.create_post',
            return_value={'topic_id': 10},
        ):
            response = browser.post(
                '/forum/topics',
                {'document_id': taggable.waypoint_id, 'lang': 'en'},
                user='contributor',
            )
        check_snapshot('forum_topics', response)


@pytest.fixture
def external_id(session, user_ids):
    """Add an SSO key and the external id of the contributor."""
    session.add(SsoKey(domain='external.domain.net', key=hash_token('sso_test_key')))
    contributor = session.get(User, user_ids['contributor'])
    external_id = SsoExternalId(
        domain='external.domain.net', external_id='1', user=contributor
    )
    session.add(external_id)
    session.flush()
    return external_id


@pytest.mark.usefixtures('discourse')
class TestSso:
    @contract(('POST', '/sso_sync'), ('POST', '/sso_login'))
    def test_sync_then_login(self, session, browser, external_id):
        synced = browser.post(
            '/sso_sync',
            {'sso_key': 'sso_test_key', 'external_id': '1'},
        )
        check_snapshot('sso_sync', synced)
        session.expire(external_id)
        external_id.expire = sso_expire_from_now()
        session.flush()
        # the token is in the URL answered: the database keeps its hash
        token = parse_qs(urlparse(synced.json['url']).query)['token'][0]
        login = browser.post('/sso_login', {'token': token})
        check_snapshot('sso_login', login)
