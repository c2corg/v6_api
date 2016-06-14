# -*- coding: utf-8 -*-
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import search_documents, elasticsearch_config
from nose.plugins.attrib import attr

from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile, USERPROFILE_TYPE

from c2corg_api.tests.views import BaseTestRest
from c2corg_api.security.discourse_client import (
    APIDiscourseClient, get_discourse_client, set_discourse_client)

from urllib.parse import urlparse, parse_qs

import re

from unittest.mock import Mock, MagicMock


class TestUserRest(BaseTestRest):

    def __init__(self, *args, **kwargs):
        BaseTestRest.__init__(self, *args, **kwargs)
        self.original_discourse_client = get_discourse_client(self.settings)

    def setUp(self):  # noqa
        self._prefix = "/users"
        self._model = User
        BaseTestRest.setUp(self)
        self.set_discourse_up()

    def set_discourse_client_mock(self, client):
        self.discourse_client = client
        set_discourse_client(client)

    def set_discourse_not_mocked(self):
        self.set_discourse_client_mock(self.original_discourse_client)

    def set_discourse_up(self):
        # unittest.Mock works great with a completly fake object
        mock = Mock()
        mock.redirect_without_nonce = MagicMock()
        mock.redirect = MagicMock()
        mock.sso_sync = MagicMock()
        self.set_discourse_client_mock(mock)

    def set_discourse_down(self):
        # unittest.Mock wants a concrete object to throw correctly
        mock = APIDiscourseClient(self.settings)
        mock.redirect_without_nonce = MagicMock(side_effect=Exception)
        mock.redirect = MagicMock(side_effect=Exception)
        mock.sso_sync = MagicMock(side_effect=Exception)
        self.set_discourse_client_mock(mock)

    def extract_urls(self, data):
        return re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+[0-9a-zA-Z]', data)  # noqa

    def extract_nonce(self, key):
        validation_url = self.extract_urls(self.get_last_email().body)[0]
        query = parse_qs(urlparse(validation_url).query)
        nonce = query[key][0]
        return nonce

    def test_always_register_non_validated_users(self):
        request_body = {
            'username': 'test', 'forum_username': 'test',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email_validated': True,
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        # First succeed in creating a new user
        body = self.app_post_json(url, request_body, status=200).json
        user_id = body.get('id')
        user = self.session.query(User).get(user_id)
        self.assertFalse(user.email_validated)

    def test_register_default_lang(self):
        request_body = {
            'username': 'test', 'forum_username': 'test',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        body = self.app_post_json(url, request_body, status=200).json
        user_id = body.get('id')
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.lang, 'fr')

    def test_register_passed_lang(self):
        request_body = {
            'username': 'test', 'forum_username': 'test',
            'lang': 'en',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        body = self.app_post_json(url, request_body, status=200).json
        user_id = body.get('id')
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.lang, 'en')

    def test_register_invalid_lang(self):
        request_body = {
            'username': 'test', 'forum_username': 'test',
            'lang': 'nn',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'
        self.app_post_json(url, request_body, status=400).json

    def test_update_preferred_lang(self):
        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.lang, 'fr')

        request_body = {
            'lang': 'en'
        }
        url = self._prefix + '/update_preferred_language'
        self.post_json_with_contributor(url, request_body, status=200)

        self.session.expunge(user)
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.lang, 'en')

    def test_register_discourse_up(self):
        request_body = {
            'username': 'test', 'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        # First succeed in creating a new user
        email_count = self.get_email_box_length()
        body = self.app_post_json(url, request_body, status=200).json
        self.assertBodyEqual(body, 'username', 'test')
        self.assertBodyEqual(body, 'forum_username', 'testf')
        self.assertBodyEqual(body, 'name', 'Max Mustermann')
        self.assertBodyEqual(body, 'email', 'some_user@camptocamp.org')
        self.assertNotIn('password', body)
        self.assertIn('id', body)
        user_id = body.get('id')
        user = self.session.query(User).get(user_id)
        self.assertIsNotNone(user)
        self.assertFalse(user.email_validated)
        profile = self.session.query(UserProfile).get(user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(len(profile.versions), 1)
        email_count_after = self.get_email_box_length()
        self.assertEqual(email_count_after, email_count + 1)

        self.assertEqual(user.lang, 'fr')
        # Simulate confirmation email validation
        nonce = self.extract_nonce('validate_register_email')
        url_api_validation = '/users/validate_register_email/%s' % nonce
        self.app_post_json(url_api_validation, {}, status=200)

        # Need to expunge the profile and user so that the latest
        # version (the one from the view) is actually picked up.
        self.session.expunge(profile)
        self.session.expunge(user)
        profile = self.session.query(UserProfile).get(user_id)
        self.assertEqual(len(profile.versions), 1)
        user = self.session.query(User).get(user_id)
        self.assertTrue(user.email_validated)

        # Now reject non unique attributes
        body = self.app_post_json(url, request_body, status=400).json
        self.assertErrorsContain(body, 'email')
        self.assertErrorsContain(body, 'username')

        # Require username, password and email attributes
        body = self.app_post_json(url, {}, status=400).json
        self.assertErrorsContain(body, 'email')
        self.assertErrorsContain(body, 'username')
        self.assertErrorsContain(body, 'password')

        # Usage of utf8 password
        request_utf8 = {
            'username': 'utf8', 'name': 'utf8', 'forum_username': 'utf8f',
            'password': 'élève 日本',
            'email': 'utf8@camptocamp.org'
        }
        body = self.app_post_json(url, request_utf8, status=200).json

    def test_register_search_index(self):
        """Tests that user accounts are only indexed once they are confirmed.
        """
        request_body = {
            'username': 'test', 'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        body = self.app_post_json(url, request_body, status=200).json
        self.assertIn('id', body)
        user_id = body.get('id')

        # check that the profile is not inserted in the search index
        sync_es(self.session)
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id,
            index=elasticsearch_config['index'], ignore=404)
        self.assertIsNone(search_doc)

        # Simulate confirmation email validation
        nonce = self.extract_nonce('validate_register_email')
        url_api_validation = '/users/validate_register_email/%s' % nonce
        self.app_post_json(url_api_validation, {}, status=200)

        # check that the profile is inserted in the index after confirmation
        self.sync_es()
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id,
            index=elasticsearch_config['index'])
        self.assertIsNotNone(search_doc)

        self.assertIsNotNone(search_doc['doc_type'])
        self.assertEqual(search_doc['title_fr'], 'test Max Mustermann testf')

    def test_register_discourse_down(self):
        self.set_discourse_down()
        request_body = {
            'username': 'test', 'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }
        url = self._prefix + '/register'

        # First succeed in creating a new user
        self.app_post_json(url, request_body, status=200)

        # Simulate confirmation email validation
        nonce = self.extract_nonce('validate_register_email')
        url_api_validation = '/users/validate_register_email/%s' % nonce

        self.app_post_json(url_api_validation, {}, status=500)

    def test_forgot_password_non_existing_email(self):
        url = '/users/request_password_change'
        body = self.app_post_json(url, {
            'email': 'non_existing_oeuhsaeuh@camptocamp.org'}, status=400).json
        self.assertErrorsContain(body, 'email', 'No user with this email')

    def test_forgot_password_discourse_up(self):
        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)
        initial_encoded_password = user.password

        url = '/users/request_password_change'
        self.app_post_json(url, {
            'email': user.email}, status=200).json

        # Simulate confirmation email validation
        nonce = self.extract_nonce('change_password')
        url_api_validation = '/users/validate_new_password/%s' % nonce

        self.app_post_json(url_api_validation, {
            'password': 'new pass'
            }, status=200)

        self.session.expunge(user)
        user = self.session.query(User).get(user_id)
        self.assertIsNone(user.validation_nonce)
        modified_encoded_password = user.password

        self.assertTrue(initial_encoded_password != modified_encoded_password)

    def test_forgot_password_discourse_down(self):
        self.set_discourse_down()
        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)

        url = '/users/request_password_change'
        self.app_post_json(url, {
            'email': user.email}, status=200).json

        # Simulate confirmation email validation
        nonce = self.extract_nonce('change_password')
        url_api_validation = '/users/validate_new_password/%s' % nonce

        # Succeed anyway since only the password has changed
        self.app_post_json(url_api_validation, {
            'password': 'new pass'
            }, status=200)

    @attr('jobs')
    def test_purge_accounts(self):
        from c2corg_api.jobs.purge_non_activated_accounts import purge_account
        from datetime import datetime
        request_body = {
            'username': 'test', 'forum_username': 'testf',
            'name': 'Max Mustermann',
            'password': 'super secret',
            'email': 'some_user@camptocamp.org'
        }

        now = datetime.utcnow()
        query = self.session.query(User).filter(User.username == 'test')

        # First succeed in creating a new user
        url = '/users/register'
        self.app_post_json(url, request_body, status=200)

        # Then simulate a scheduled call to purge accounts
        purge_account(self.session)

        # The user should still exist
        user = query.one()

        # Expire nonce
        user.validation_nonce_expire = now
        self.session.commit()

        # The user should be removed
        purge_account(self.session)
        self.assertEqual(0, query.count())

    @attr('jobs')
    def test_purge_tokens(self):
        from c2corg_api.jobs.purge_expired_tokens import purge_token
        from datetime import datetime
        body = self.login('moderator', status=200).json
        token_value = body['token']

        query = self.session.query(Token).filter(Token.value == token_value)

        now = datetime.utcnow()

        # Token should still exist
        purge_token(self.session)
        self.assertEqual(1, query.count())

        # Expire token
        token = query.one()
        token.expire = now

        # The token should be removed
        purge_token(self.session)
        self.assertEqual(0, query.count())

    def login(self, username, password=None, status=200, sso=None, sig=None,
              discourse=None):
        if not password:
            password = self.global_passwords[username]

        request_body = {
            'username': username,
            'password': password
            }

        if sso:
            request_body['sso'] = sso
        if sig:
            request_body['sig'] = sig
        if discourse:
            request_body['discourse'] = discourse

        url = '/users/login'
        response = self.app_post_json(url, request_body, status=status)
        return response

    def test_login_success_discourse_up(self):
        body = self.login('moderator', status=200).json
        self.assertTrue('token' in body)

    def test_login_success_discourse_down(self):
        # Topoguide login allowed even if Discourse is down.
        body = self.login('moderator', status=200).json
        self.assertTrue('token' in body)

    def test_login_discourse_success(self):
        self.set_discourse_not_mocked()
        # noqa See https://meta.discourse.org/t/official-single-sign-on-for-discourse/13045
        sso = "bm9uY2U9Y2I2ODI1MWVlZmI1MjExZTU4YzAwZmYxMzk1ZjBjMGI%3D%0A"
        sig = "2828aa29899722b35a2f191d34ef9b3ce695e0e6eeec47deb46d588d70c7cb56"  # noqa

        moderator = self.session.query(User).filter(
                User.username == 'moderator').one()
        redirect1 = self.discourse_client.redirect(moderator, sso, sig)

        body = self.login('moderator', sso=sso, sig=sig, discourse=True).json
        self.assertTrue('token' in body)
        redirect2 = body['redirect']

        self.assertEqual(redirect1, redirect2)

    def test_login_failure(self):
        body = self.login('moderator', password='invalid', status=403).json
        self.assertEqual(body['status'], 'error')

    def assertExpireAlmostEqual(self, expire, days, seconds_delta):  # noqa
        import time
        now = int(round(time.time()))
        expected = days * 24 * 3600 + now  # 14 days from now
        if (abs(expected - expire) > seconds_delta):
            raise self.failureException(
                '%r == %r within %r seconds' %
                (expected, expire, seconds_delta))

    def test_login_logout_success(self):
        body = self.login('moderator').json
        token = body['token']
        expire = body['expire']
        self.assertExpireAlmostEqual(expire, 14, 5)

        body = self.post_json_with_token('/users/logout', token)

    def test_renew_success(self):
        restricted_url = '/users/' + str(self.global_userids['contributor'])
        token = self.global_tokens['contributor']

        body = self.post_json_with_token('/users/renew', token)
        expire = body['expire']
        self.assertExpireAlmostEqual(expire, 14, 5)

        token2 = body['token']
        body = self.get_json_with_token(restricted_url, token2, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def test_renew_token_different_success(self):
        # Tokens created in the same second are identical
        restricted_url = '/users/' + str(self.global_userids['contributor'])

        token1 = self.login('contributor').json['token']

        import time
        print('Waiting for more than 1s to get a different token')
        time.sleep(1.01)

        token2 = self.post_json_with_token('/users/renew', token1)['token']
        self.assertNotEquals(token1, token2)

        body = self.get_json_with_token(restricted_url, token2, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

        self.post_json_with_token('/users/logout', token1)
        self.post_json_with_token('/users/logout', token2)

    def test_restricted_request(self):
        url = '/users/' + str(self.global_userids['contributor'])
        body = self.get_json_with_contributor(url, status=200)
        self.assertBodyEqual(body, 'username', 'contributor')

    def test_restricted_request_unauthenticated(self):
        url = '/users/' + str(self.global_userids['contributor'])
        self.app.get(url, status=403)

    def test_read_account_info(self):
        url = '/users/account'
        body = self.get_json_with_contributor(url, status=200)
        self.assertBodyEqual(body, 'name', 'Contributor')
        self.assertBodyEqual(body, 'email', 'contributor@camptocamp.org')
        self.assertBodyEqual(body, 'forum_username', 'contributor')

    def _update_account_field_discourse_up(self, field, value):
        url = '/users/account'
        currentpassword = self.global_passwords['contributor']

        data = {
            'currentpassword': currentpassword
        }
        data[field] = value
        self.post_json_with_contributor(url, data, status=200)

        self.assertEqual(1, int(self.discourse_client.sso_sync.called_count))

    def _update_account_field_discourse_down(self, field, value):
        self.set_discourse_down()

        url = '/users/account'
        currentpassword = self.global_passwords['contributor']

        data = {
            'currentpassword': currentpassword
        }
        data[field] = value
        self.post_json_with_contributor(url, data, status=500)

        self.assertEqual(1, int(self.discourse_client.sso_sync.called_count))

    def test_update_account_email_discourse_up(self):
        email_count = self.get_email_box_length()

        new_email = 'superemail@localhost.localhost'
        self._update_account_field_discourse_up('email', new_email)

        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.email_to_validate, new_email)
        self.assertNotEqual(user.email, new_email)

        email_count_after = self.get_email_box_length()
        self.assertEqual(email_count_after, email_count + 1)

        # Simulate confirmation email validation
        nonce = self.extract_nonce('validate_change_email')
        url_api_validation = '/users/validate_change_email/%s' % nonce
        self.app_post_json(url_api_validation, {}, status=200)

        self.session.expunge(user)
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.email, new_email)
        self.assertIsNone(user.validation_nonce)

    def test_update_account_email_discourse_down(self):
        new_email = 'superemail@localhost.localhost'
        self._update_account_field_discourse_down('email', new_email)

    def test_update_account_name_discourse_up(self):
        self._update_account_field_discourse_up('name', 'changed')

        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.name, 'changed')

        # check that the search index is updated with the new name
        self.sync_es()
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id,
            index=elasticsearch_config['index'])

        self.assertIsNotNone(search_doc['doc_type'])
        self.assertEqual(
            search_doc['title_en'], 'contributor changed contributor')

    def test_update_account_name_discourse_down(self):
        self._update_account_field_discourse_down('name', 'changed')

    def test_update_account_forum_username_discourse_up(self):
        self._update_account_field_discourse_up('forum_username', 'changed')

        user_id = self.global_userids['contributor']
        user = self.session.query(User).get(user_id)
        self.assertEqual(user.forum_username, 'changed')

    def test_update_account_forum_username_discourse_down(self):
        self._update_account_field_discourse_down('forum_username', 'changed')
