import base64
import datetime
import hashlib
import hmac
import time
from unittest.mock import Mock, patch
from urllib.parse import quote, urlencode

import jwt
import pytest

from c2corg_api.httpexceptions import HTTPBadRequest

# from pytest import mark
from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.security.discourse_client import (
    DisabledDiscourseClient,
)
from c2corg_api.security.roles import (
    add_token,
    create_claims,
    hash_token,
    log_validated_user_i_know_what_i_do,
)
from c2corg_api.tests import (
    assert_body_equal,
    assert_errors_contain,
    errors_of,
    extract_nonce,
    get_json_with_token,
    post_json_with_token,
    send_json,
    sync_es_queue,
)

pytestmark = pytest.mark.usefixtures('discourse')

forum_username_tests = {
    # min length
    'a': 'Shorter than minimum length 3',
    'a' * 3: False,
    # max length
    'a' * 26: 'Longer than maximum length 25',
    'a' * 25: False,
    # valid characters
    'test/test': 'Contain invalid character(s)',
    'test.test-test_test': False,
    # first char
    '-test': 'First character is invalid',
    # last char
    'test.': 'Last character is invalid',
    # double special char
    'test__test': ('Contains consecutive special characters'),
    # confusing suffix
    'test.jpg': 'Ended by confusing suffix',
}


PREFIX = '/users'


def login(
    client,
    settings,
    passwords,
    username,
    password=None,
    status=200,
    sso=None,
    sig=None,
    discourse=None,
    accept_tos=None,
):
    if not password:
        password = passwords[username]

    request_body = {'username': username, 'password': password}

    if sso:
        request_body['sso'] = sso
    if sig:
        request_body['sig'] = sig
    if discourse:
        request_body['discourse'] = discourse
    if accept_tos:
        request_body['accept_tos'] = accept_tos

    url = '/users/login'
    response = send_json(client, 'post', url, request_body, status=status)
    return response


def _build_signed_sso_payload(discourse, return_sso_url):
    payload = urlencode(
        {
            'nonce': 'cb68251eefb5211e58c00ff1395f0c0b',
            'return_sso_url': return_sso_url,
        }
    )
    b64_payload = base64.b64encode(payload.encode('utf-8')).decode('ascii')
    sig = hmac.new(
        discourse.client.sso_key.encode('utf-8'),
        b64_payload.encode('utf-8'),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return quote(b64_payload), sig


def assert_expire_almost_equal(expire, days, seconds_delta):
    now = int(round(time.time()))
    expected = days * 24 * 3600 + now  # 14 days from now
    if abs(expected - expire) > seconds_delta:
        raise AssertionError(
            f'{expected!r} == {expire!r} within {seconds_delta!r} seconds'
        )


def _login_remember(client, passwords, remember, status=200):
    body = {
        'username': 'contributor',
        'password': passwords['contributor'],
        'remember': remember,
    }
    return send_json(client, 'post', '/users/login', body, status=status).json


def _lifetime(settings, token):
    claims = jwt.decode(token, settings['jwt.private_key'], algorithms=['HS256'])
    return claims['exp'] - claims['iat']


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_always_register_non_validated_users(_send_email, client, session):
    request_body = {
        'username': 'test',
        'forum_username': 'test',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email_validated': True,
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    # First succeed in creating a new user
    body = send_json(client, 'post', url, request_body, status=200).json
    user_id = body.get('id')
    user = session.get(User, user_id)
    assert not user.email_validated
    assert user.tos_validated is not None
    _send_email.check_call_once()


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_default_lang(_send_email, client, session):
    request_body = {
        'username': 'test',
        'forum_username': 'test',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    body = send_json(client, 'post', url, request_body, status=200).json
    user_id = body.get('id')
    user = session.get(User, user_id)
    assert user.lang == 'fr'
    _send_email.check_call_once()


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_passed_lang(_send_email, client, session):
    request_body = {
        'username': 'test',
        'forum_username': 'test',
        'lang': 'en',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    body = send_json(client, 'post', url, request_body, status=200).json
    user_id = body.get('id')
    user = session.get(User, user_id)
    assert user.lang == 'en'
    _send_email.check_call_once()


def test_register_invalid_lang(client):
    request_body = {
        'username': 'test',
        'forum_username': 'test',
        'lang': 'nn',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'
    send_json(client, 'post', url, request_body, status=422).json


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_forum_username_validity(_send_email, client):
    url = PREFIX + '/register'
    i = 0
    for forum_username, value in forum_username_tests.items():
        i += 1
        request_body = {
            'username': f'test{i}',
            'forum_username': forum_username,
            'name': f'Max Mustermann{i}',
            'password': 'Super$ecret1',  # nosec B105 (a test password)
            'email': f'some_user{i}@camptocamp.org',
        }
        if value is False:
            send_json(client, 'post', url, request_body, status=200).json
        else:
            # the schema checks it: 422
            json = send_json(client, 'post', url, request_body, status=422).json
            assert errors_of(json)[0]['description'] == value


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_forum_username_unique(_send_email, client):
    request_body = {
        'username': 'test',
        'forum_username': 'Contributor',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'
    json = send_json(client, 'post', url, request_body, status=400).json
    assert json['errors'][0]['description'] == 'already used forum_username'


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_stripped_username(_send_email, client, session):
    request_body = {
        'username': ' contributor ',
        'forum_username': 'Foo',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'
    json = send_json(client, 'post', url, request_body, status=400).json
    assert json['errors'][0]['description'] == 'This username already exists'

    request_body = {
        'username': ' username with spaces ',
        'forum_username': 'Spaceman',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'space@camptocamp.org',
    }
    url = PREFIX + '/register'
    body = send_json(client, 'post', url, request_body, status=200).json
    assert_body_equal(body, 'username', 'username with spaces')
    user_id = body.get('id')
    user = session.get(User, user_id)
    assert user is not None
    assert user.username == 'username with spaces'


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_username_email_not_equals_email(_send_email, client):
    request_body = {
        'username': 'someone_else@camptocamp.org',
        'forum_username': 'Contributor4',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'
    json = send_json(client, 'post', url, request_body, status=400).json
    assert (
        json['errors'][0]['description']
        == 'An email address used as username should be the '
        + 'same as the one used as the account email address.'
    )


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_username_email_equals_email(_send_email, client):
    request_body = {
        'username': 'some_user@camptocamp.org',
        'forum_username': 'Contributor4',
        'name': 'Frankie Vincent',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'
    send_json(client, 'post', url, request_body, status=200)


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_invalid_email(_send_email, client):
    request_body = {
        'username': 'test',
        'forum_username': 'Contributor',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_useratcamptocamp.org',
    }
    url = PREFIX + '/register'
    json = send_json(client, 'post', url, request_body, status=422).json
    assert errors_of(json)[0]['description'] == 'Invalid email address'


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_discourse_up(_send_email, client, session):
    request_body = {
        'username': 'test',
        'forum_username': 'testf',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    # First succeed in creating a new user
    body = send_json(client, 'post', url, request_body, status=200).json
    assert_body_equal(body, 'username', 'test')
    assert_body_equal(body, 'forum_username', 'testf')
    assert_body_equal(body, 'name', 'Max Mustermann')
    assert_body_equal(body, 'email', 'some_user@camptocamp.org')
    assert 'password' not in body
    assert 'id' in body
    user_id = body.get('id')
    user = session.get(User, user_id)
    assert user is not None
    assert not user.email_validated
    profile = session.get(UserProfile, user_id)
    assert profile is not None
    assert len(profile.versions) == 1
    _send_email.check_call_once()

    assert user.lang == 'fr'
    # Simulate confirmation email validation
    nonce = extract_nonce(_send_email, 'validate_register_email')
    url_api_validation = f'/users/validate_register_email/{nonce}'
    send_json(client, 'post', url_api_validation, {}, status=200)

    # Need to expunge the profile and user so that the latest
    # version (the one from the view) is actually picked up.
    session.expunge(profile)
    session.expunge(user)
    profile = session.get(UserProfile, user_id)
    assert len(profile.versions) == 1
    user = session.get(User, user_id)
    assert user.email_validated

    # Now reject non unique attributes
    body = send_json(client, 'post', url, request_body, status=400).json
    assert_errors_contain(body, 'email')
    assert_errors_contain(body, 'username')

    # Require username and email attributes (the schema: 422)
    body = send_json(client, 'post', url, {}, status=422).json
    assert_errors_contain(body, 'email')
    assert_errors_contain(body, 'username')
    # and the password (its validator, with a valid body: 400)
    without_password = {**request_body, 'username': 'other', 'email': 'o@x.org'}
    del without_password['password']
    body = send_json(client, 'post', url, without_password, status=400).json
    assert_errors_contain(body, 'password', 'Required')

    # Usage of utf8 password
    request_utf8 = {
        'username': 'utf8',
        'name': 'utf8',
        'forum_username': 'utf8f',
        # Test fixture, not a real credential; exercises non-ASCII
        # password handling.
        'password': 'Élève 日本!1234',  # nosec
        'email': 'utf8@camptocamp.org',
    }
    body = send_json(client, 'post', url, request_utf8, status=200).json


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_search_index(_send_email, client, session, queue_config):
    """Tests that user accounts are only indexed once they are confirmed."""
    request_body = {
        'username': 'test',
        'forum_username': 'testf',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    body = send_json(client, 'post', url, request_body, status=200).json
    assert 'id' in body
    user_id = body.get('id')

    # check that the profile is not inserted in the search index
    sync_es(session)
    search_doc = search_documents[USERPROFILE_TYPE].get(
        id=user_id, index=elasticsearch_config['index'], ignore=404
    )
    assert search_doc is None

    # Simulate confirmation email validation
    nonce = extract_nonce(_send_email, 'validate_register_email')
    url_api_validation = f'/users/validate_register_email/{nonce}'
    send_json(client, 'post', url_api_validation, {}, status=200)

    # check that the profile is inserted in the index after confirmation
    sync_es_queue(session, queue_config)
    search_doc = search_documents[USERPROFILE_TYPE].get(
        id=user_id, index=elasticsearch_config['index']
    )
    assert search_doc is not None

    assert search_doc['doc_type'] is not None
    assert search_doc['title_fr'] == 'Max Mustermann testf'


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_register_discourse_down(_send_email, client, settings, discourse):
    discourse.down()
    request_body = {
        'username': 'test',
        'forum_username': 'testf',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }
    url = PREFIX + '/register'

    # First succeed in creating a new user
    send_json(client, 'post', url, request_body, status=200)

    # Simulate confirmation email validation
    nonce = extract_nonce(_send_email, 'validate_register_email')
    url_api_validation = f'/users/validate_register_email/{nonce}'

    send_json(client, 'post', url_api_validation, {}, status=500)


def test_forgot_password_non_existing_email(client):
    url = '/users/request_password_change'
    body = send_json(
        client,
        'post',
        url,
        {'email': 'non_existing_oeuhsaeuh@camptocamp.org'},
        status=400,
    ).json
    assert_errors_contain(body, 'email', 'No user with this email')


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_forgot_password_discourse_up(_send_email, client, session, user_ids):
    user_id = user_ids['contributor']
    user = session.get(User, user_id)
    initial_encoded_password = user.password

    url = '/users/request_password_change'
    send_json(client, 'post', url, {'email': user.email}, status=200).json

    _send_email.check_call_once()

    # Simulate confirmation email validation
    nonce = extract_nonce(_send_email, 'change_password')
    url_api_validation = f'/users/validate_new_password/{nonce}'

    send_json(
        client,
        'post',
        url_api_validation,
        {
            'password': 'New$Password1'  # nosec - test fixture
        },
        status=200,
    )

    session.expunge(user)
    user = session.get(User, user_id)
    assert user.validation_nonce is None
    modified_encoded_password = user.password

    assert initial_encoded_password != modified_encoded_password


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_forgot_password_discourse_down(
    _send_email, client, session, settings, user_ids, discourse
):
    discourse.down()
    user_id = user_ids['contributor']
    user = session.get(User, user_id)

    url = '/users/request_password_change'
    send_json(client, 'post', url, {'email': user.email}, status=200).json

    _send_email.check_call_once()

    # Simulate confirmation email validation
    nonce = extract_nonce(_send_email, 'change_password')
    url_api_validation = f'/users/validate_new_password/{nonce}'

    # Succeed anyway since only the password has changed
    send_json(
        client,
        'post',
        url_api_validation,
        {
            'password': 'New$Password1'  # nosec - test fixture
        },
        status=200,
    )


def test_forgot_password_blocked_account(client, session, user_ids):
    user_id = user_ids['contributor']
    user = session.get(User, user_id)
    user.blocked = True
    session.flush()

    url = '/users/request_password_change'
    send_json(client, 'post', url, {'email': user.email}, status=403)


@patch('c2corg_api.emails.email_service.EmailService._send_email')
def test_purge_accounts(_send_email, client, session):
    from datetime import datetime

    from c2corg_api.jobs.purge_non_activated_accounts import purge_account

    request_body = {
        'username': 'test',
        'forum_username': 'testf',
        'name': 'Max Mustermann',
        'password': 'Super$ecret1',  # nosec B105 (a test password)
        'email': 'some_user@camptocamp.org',
    }

    now = datetime.utcnow()
    query = session.query(User).filter(User.username == 'test')

    # First succeed in creating a new user
    url = '/users/register'
    send_json(client, 'post', url, request_body, status=200)

    # Then simulate a scheduled call to purge accounts
    purge_account()

    # The user should still exist
    user = query.one()

    # Expire nonce
    user.validation_nonce_expire = now
    session.commit()

    # The user should be removed
    purge_account()
    assert 0 == query.count()


def test_purge_tokens(client, session, settings, passwords):
    from datetime import datetime

    from c2corg_api.jobs.purge_expired_tokens import purge_token

    body = login(client, settings, passwords, 'moderator', status=200).json
    token_value = body['token']

    query = session.query(Token).filter(Token.value == hash_token(token_value))

    now = datetime.utcnow()

    # Token should still exist
    purge_token()
    assert 1 == query.count()

    # Expire token
    token = query.one()
    token.expire = now
    session.commit()

    # The token should be removed
    purge_token()
    assert 0 == query.count()


def test_purge_tokens_logs_out_from_the_forum(
    client, session, settings, user_ids, passwords
):
    from c2corg_api.jobs import purge_expired_tokens

    contributor = user_ids['contributor']
    moderator = user_ids['moderator']
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)
    # the contributor: every token expired (the global one too)
    login(client, settings, passwords, 'contributor')
    session.query(Token).filter(Token.userid == contributor).update({'expire': past})
    # the moderator: one token expired, the global one still valid
    moderator_token = login(client, settings, passwords, 'moderator').json['token']
    session.query(Token).filter(Token.value == hash_token(moderator_token)).update(
        {'expire': past}
    )
    session.commit()

    forum = Mock()
    with (
        patch.object(purge_expired_tokens, 'get_discourse_client', return_value=forum),
        patch.object(purge_expired_tokens.time, 'sleep'),
    ):
        purge_expired_tokens.purge_token(settings)

    forum.logout.assert_called_once_with(contributor)
    assert session.query(Token).filter(Token.userid == contributor).count() == 0
    assert session.query(Token).filter(Token.userid == moderator).count() == 1


def test_logout_from_forum(settings):
    from c2corg_api.jobs import purge_expired_tokens

    forum = Mock()
    forum.logout.side_effect = [Exception('not on the forum'), None]
    with (
        patch.object(purge_expired_tokens, 'get_discourse_client', return_value=forum),
        patch.object(purge_expired_tokens.time, 'sleep') as sleep,
    ):
        purge_expired_tokens.logout_from_forum(settings, [3, 4])

    # a failure does not stop the others
    assert [c.args for c in forum.logout.call_args_list] == [(3,), (4,)]
    sleep.assert_called_once_with(purge_expired_tokens.FORUM_LOGOUT_INTERVAL)


def test_login_success_discourse_up(client, settings, passwords):
    body = login(client, settings, passwords, 'moderator', status=200).json
    assert 'token' in body


def test_login_success_discourse_down(client, settings, passwords):
    # Topoguide login allowed even if Discourse is down.
    body = login(client, settings, passwords, 'moderator', status=200).json
    assert 'token' in body


def test_login_discourse_disabled(client, settings, passwords, discourse):
    """Log in, without a forum session to open, when the forum is disabled."""
    discourse.use(DisabledDiscourseClient())
    body = login(
        client, settings, passwords, 'moderator', discourse=True, status=200
    ).json
    assert 'token' in body
    assert body.get('redirect_internal') is None


def test_login_success_use_email(client, settings, passwords):
    # login allowed if providing the email instead of login
    body = login(
        client,
        settings,
        passwords,
        'moderator@camptocamp.org',
        passwords['moderator'],
        status=200,
    ).json
    assert 'token' in body


def test_login_success_with_legacy_short_password(
    client, session, settings, user_ids, passwords
):
    # Regression test: MINIMUM_PASSWORD_LENGTH/complexity are policy
    # for *setting* a password (register, reset), not for checking an
    # existing one - an account created before this policy existed
    # must still be able to log in with its original short/simple
    # password.
    contributor = session.get(User, user_ids['contributor'])
    # Test fixture, not a real credential; deliberately weak/short
    # to simulate a pre-policy account.
    contributor.password = 'abc'  # nosec
    session.flush()

    body = login(
        client,
        settings,
        passwords,
        'contributor',
        password='abc',
        status=200,  # nosec B106 (a test password)
    ).json
    assert 'token' in body


def test_login_with_a_stored_password_not_a_bcrypt_hash(
    client, session, settings, user_ids, passwords
):
    # #592: "Invalid salt" answered a 500
    contributor = session.get(User, user_ids['contributor'])
    contributor._password = 'not a bcrypt hash'  # nosec B105
    session.flush()

    body = login(client, settings, passwords, 'contributor', status=401).json
    assert body['status'] == 'error'


def test_login_blocked_account(client, session, settings, user_ids, passwords):
    contributor = session.get(User, user_ids['contributor'])
    contributor.blocked = True
    session.flush()

    body = login(client, settings, passwords, 'contributor', status=403).json
    assert_errors_contain(body, 'Forbidden', 'account blocked')


def test_login_discourse_success(client, session, settings, passwords, discourse):
    discourse.restore()
    # return_sso_url tells the SSO provider (us) which Discourse
    # instance to redirect back to - not a real secret, only used to
    # sign this test's own fixture.
    discourse.client.sso_key = 'test_only_shared_secret_not_a_real_credential'
    return_sso_url = 'https://forum-test.example.org/session/sso_login'
    discourse.client.allowed_sso_hosts = {'forum-test.example.org'}

    sso, sig = _build_signed_sso_payload(discourse, return_sso_url)

    moderator = session.query(User).filter(User.username == 'moderator').one()
    redirect1 = discourse.client.redirect(moderator, sso, sig)
    assert redirect1.startswith(return_sso_url + '?')

    body = login(
        client, settings, passwords, 'moderator', sso=sso, sig=sig, discourse=True
    ).json
    assert 'token' in body
    redirect2 = body['redirect']

    assert redirect1 == redirect2


def test_login_discourse_rejects_unlisted_return_sso_url(session, discourse):
    discourse.restore()
    discourse.client.sso_key = 'test_only_shared_secret_not_a_real_credential'
    discourse.client.allowed_sso_hosts = {'forum-test.example.org'}

    # correctly signed (same secret), but pointing somewhere not on
    # the allowlist - must be rejected even though the signature is
    # valid, otherwise a leaked sso_secret could redirect an
    # authenticated user's browser anywhere.
    sso, sig = _build_signed_sso_payload(
        discourse, 'https://not-allowed.example.org/session/sso_login'
    )

    moderator = session.query(User).filter(User.username == 'moderator').one()
    with pytest.raises(HTTPBadRequest):
        discourse.client.redirect(moderator, sso, sig)


def test_discourse_redirect_success(client, session, tokens, discourse):
    discourse.restore()
    discourse.client.sso_key = 'test_only_shared_secret_not_a_real_credential'
    return_sso_url = 'https://forum-test.example.org/session/sso_login'
    discourse.client.allowed_sso_hosts = {'forum-test.example.org'}

    sso, sig = _build_signed_sso_payload(discourse, return_sso_url)

    moderator = session.query(User).filter(User.username == 'moderator').one()
    expected = discourse.client.redirect(moderator, sso, sig)

    body = post_json_with_token(
        client,
        '/users/discourse-redirect',
        tokens['moderator'],
        {'sso': sso, 'sig': sig},
        status=200,
    )
    assert body['redirect'] == expected


def test_discourse_redirect_bad_signature(client, tokens, discourse):
    discourse.restore()
    discourse.client.sso_key = 'test_only_shared_secret_not_a_real_credential'
    discourse.client.allowed_sso_hosts = {'forum-test.example.org'}

    sso, _ = _build_signed_sso_payload(
        discourse, 'https://forum-test.example.org/session/sso_login'
    )

    post_json_with_token(
        client,
        '/users/discourse-redirect',
        tokens['moderator'],
        {'sso': sso, 'sig': 'not-the-right-signature'},
        status=400,
    )


def test_discourse_redirect_without_return_sso_url(client, tokens, discourse):
    discourse.restore()
    discourse.client.sso_key = 'test_only_shared_secret_not_a_real_credential'
    payload = base64.b64encode(b'nonce=cb68251e').decode('ascii')
    sig = hmac.new(
        discourse.client.sso_key.encode('utf-8'),
        payload.encode('utf-8'),
        digestmod=hashlib.sha256,
    ).hexdigest()

    post_json_with_token(
        client,
        '/users/discourse-redirect',
        tokens['moderator'],
        {'sso': quote(payload), 'sig': sig},
        status=400,
    )


def test_log_in_a_user_whose_email_is_not_validated(session, user_ids):
    contributor = session.get(User, user_ids['contributor'])
    contributor.email_validated = False
    session.flush()

    with pytest.raises(ValueError):
        log_validated_user_i_know_what_i_do(contributor, None)


def test_discourse_redirect_unauthenticated(client):
    send_json(
        client,
        'post',
        '/users/discourse-redirect',
        {'sso': 'x', 'sig': 'y'},
        status=403,
    )


def test_login_failure(client, settings, passwords):
    body = login(
        client,
        settings,
        passwords,
        'moderator',
        password='invalid_password',  # nosec B106 (a test password)
        status=401,
    ).json
    assert body['status'] == 'error'


def test_login_no_tos_failure(client, settings, passwords):
    body = login(
        client,
        settings,
        passwords,
        'contributornotos',
        password='some password',  # nosec B106 (a test password)
        status=403,
    ).json
    assert_errors_contain(body, 'Forbidden', 'Terms of Service need to be accepted')


def test_login_no_tos_success(client, session, settings, passwords):
    # A user which did not previously accepted ToS can login
    # if he accepts them. It is stored in the db.
    body = login(
        client,
        settings,
        passwords,
        'contributornotos',
        password='some password',  # nosec B106 (a test password)
        accept_tos=True,
        status=200,
    ).json
    assert 'token' in body
    user = session.query(User).filter(User.username == 'contributornotos').one()
    assert (
        datetime.datetime.now(datetime.UTC) - user.tos_validated
    ).total_seconds() < 5


def test_login_logout_success(client, settings, passwords):
    body = login(client, settings, passwords, 'moderator').json
    token = body['token']
    expire = body['expire']
    assert_expire_almost_equal(expire, 14, 5)

    body = post_json_with_token(client, '/users/logout', token)


def test_renew_success(client, tokens):
    token = tokens['contributor']

    body = post_json_with_token(client, '/users/renew', token)
    expire = body['expire']
    assert_expire_almost_equal(expire, 14, 5)

    token2 = body['token']
    body = get_json_with_token(client, '/users/account', token2, status=200)
    assert_body_equal(body, 'name', 'Contributor')


def test_renew_token_different_success(client, settings, passwords):
    token1 = login(client, settings, passwords, 'contributor').json['token']
    token2 = post_json_with_token(client, '/users/renew', token1)['token']
    assert token1 != token2

    body = get_json_with_token(client, '/users/account', token2, status=200)
    assert_body_equal(body, 'name', 'Contributor')

    post_json_with_token(client, '/users/logout', token2)


def test_logout_invalidates_the_token(client, settings, passwords):
    token = login(client, settings, passwords, 'contributor').json['token']
    get_json_with_token(client, '/users/account', token, status=200)

    post_json_with_token(client, '/users/logout', token)

    body = get_json_with_token(client, '/users/account', token, status=401)
    assert_errors_contain(body, 'Unauthorized', 'Invalid token')
    post_json_with_token(client, '/users/logout', token, status=401)


def test_logout_keeps_the_other_sessions(client, settings, passwords):
    # two logins, most likely in the same second
    token = login(client, settings, passwords, 'contributor').json['token']
    other_token = login(client, settings, passwords, 'contributor').json['token']
    assert token != other_token

    post_json_with_token(client, '/users/logout', token)

    get_json_with_token(client, '/users/account', other_token, status=200)


def test_only_the_hash_of_the_token_is_stored(
    client, session, settings, user_ids, passwords
):
    token = login(client, settings, passwords, 'contributor').json['token']
    assert session.query(Token).filter(Token.value == token).count() == 0
    stored = session.query(Token).filter(Token.value == hash_token(token))
    assert stored.one().userid == user_ids['contributor']


def test_a_token_stored_as_is_is_refused(client, session, settings, passwords):
    # since migration a7c3e1f05b2d, a row holds the hash of a token: a row
    # holding the token itself (a copy of the table) gives no session
    token = login(client, settings, passwords, 'contributor').json['token']
    stored = session.query(Token).filter(Token.value == hash_token(token))
    stored.one().value = token
    session.flush()

    get_json_with_token(client, '/users/account', token, status=401)


def test_login_not_remembered(client, settings, passwords):
    body = _login_remember(client, passwords, False)
    assert_expire_almost_equal(body['expire'], 1, 5)
    assert _lifetime(settings, body['token']) == 24 * 3600
    get_json_with_token(client, '/users/account', body['token'], status=200)


def test_login_remembered(client, settings, passwords):
    body = _login_remember(client, passwords, True)
    assert_expire_almost_equal(body['expire'], 14, 5)
    assert _lifetime(settings, body['token']) == 14 * 24 * 3600


def test_login_remember_as_a_string(client, passwords):
    # as every Bool: only 'false' and '0' are false
    body = _login_remember(client, passwords, 'false')
    assert_expire_almost_equal(body['expire'], 1, 5)
    body = _login_remember(client, passwords, 'yes')
    assert_expire_almost_equal(body['expire'], 14, 5)


def test_renew_keeps_the_lifetime(client, settings, passwords):
    for remember, days in ((False, 1), (True, 14)):
        token = _login_remember(client, passwords, remember)['token']
        body = post_json_with_token(client, '/users/renew', token)
        assert_expire_almost_equal(body['expire'], days, 5)
        assert _lifetime(settings, body['token']) == days * 24 * 3600


def test_renew_of_a_token_without_iat(client, session, settings, user_ids):
    # a token issued before the lifetimes (no `iat`): remembered
    user = session.get(User, user_ids['contributor'])
    exp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3)
    claims = create_claims(user, datetime.datetime.now(datetime.UTC), exp)
    del claims['iat']
    token = jwt.encode(claims, settings['jwt.private_key'], algorithm='HS256')
    add_token(token, exp, user.id)

    body = post_json_with_token(client, '/users/renew', token)
    assert_expire_almost_equal(body['expire'], 14, 5)


def test_token_check(client, settings, user_ids, passwords):
    body = login(client, settings, passwords, 'contributor').json
    token = body['token']

    checked = get_json_with_token(client, '/users/token', token)
    assert checked == {
        'user': user_ids['contributor'],
        'expire': body['expire'],
    }

    post_json_with_token(client, '/users/logout', token)
    get_json_with_token(client, '/users/token', token, status=401)


def test_token_check_of_a_blocked_user(client, session, user_ids, tokens):
    user = session.get(User, user_ids['contributor'])
    user.blocked = True
    session.flush()

    body = get_json_with_token(
        client, '/users/token', tokens['contributor'], status=403
    )
    assert_errors_contain(body, 'Forbidden', 'account blocked')


def test_token_check_without_a_token(client):
    client.get('/users/token', status=403)


def test_token_claims(client, settings, user_ids, passwords):
    before = int(time.time())
    token = login(client, settings, passwords, 'contributor').json['token']
    claims = jwt.decode(token, settings['jwt.private_key'], algorithms=['HS256'])
    assert set(claims) == {'sub', 'username', 'iat', 'exp', 'jti'}
    assert claims['sub'] == str(user_ids['contributor'])
    assert before <= claims['iat'] <= int(time.time())
    assert claims['exp'] - claims['iat'] == 14 * 24 * 3600
    assert len(claims['jti']) >= 16


def test_renew_revokes_the_old_token_after_a_minute(
    client, session, settings, passwords
):
    old_token = login(client, settings, passwords, 'contributor').json['token']
    new_token = post_json_with_token(client, '/users/renew', old_token)['token']
    assert new_token != old_token
    get_json_with_token(client, '/users/account', new_token, status=200)

    # the requests sent with it meanwhile (page loading, other tabs) pass
    get_json_with_token(client, '/users/account', old_token, status=200)
    row = session.query(Token).filter(Token.value == hash_token(old_token))
    expire = row.one().expire
    now = datetime.datetime.now(datetime.UTC)
    assert expire <= now + datetime.timedelta(minutes=1)

    # then it is refused, and cannot be renewed
    row.one().expire = now - datetime.timedelta(seconds=1)
    session.flush()
    body = get_json_with_token(client, '/users/account', old_token, status=401)
    assert_errors_contain(body, 'Unauthorized', 'Invalid token')
    post_json_with_token(client, '/users/renew', old_token, status=401)


def test_renew_keeps_the_other_sessions(client, settings, passwords):
    token = login(client, settings, passwords, 'contributor').json['token']
    other_token = login(client, settings, passwords, 'contributor').json['token']

    post_json_with_token(client, '/users/renew', token)

    get_json_with_token(client, '/users/account', other_token, status=200)


def test_renew_of_an_unknown_token(client):
    body = post_json_with_token(client, '/users/renew', 'not-a-token', status=401)
    assert_errors_contain(body, 'Unauthorized', 'Invalid token')
