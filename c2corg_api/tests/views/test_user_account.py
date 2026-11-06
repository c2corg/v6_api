from unittest.mock import patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.tests import (
    assert_body_equal,
    assert_errors_contain,
    errors_of,
    extract_nonce,
    get_json_with_contributor,
    post_json_with_contributor,
    send_json,
    sync_es_queue,
)
from c2corg_api.tests.views import scenarios
from c2corg_api.tests.views.test_user import PREFIX, forum_username_tests


@pytest.mark.usefixtures('discourse')
class TestUserAccountRest:
    def test_read_account_info(self, client):
        url = '/users/account'
        body = get_json_with_contributor(client, url, status=200)
        assert_body_equal(body, 'name', 'Contributor')
        assert_body_equal(body, 'email', 'contributor@camptocamp.org')
        assert_body_equal(body, 'forum_username', 'contributor')
        assert_body_equal(body, 'is_profile_public', False)

    def test_read_account_info_blocked_account(self, client, session, user_ids):
        contributor = session.get(User, user_ids['contributor'])
        contributor.blocked = True
        session.flush()

        body = get_json_with_contributor(client, '/users/account', status=403)
        assert_errors_contain(body, 'Forbidden', 'account blocked')

    def _update_account_field_discourse_up(
        self, discourse, client, passwords, field, value
    ):
        url = '/users/account'
        currentpassword = passwords['contributor']

        data = {'currentpassword': currentpassword}
        data[field] = value
        post_json_with_contributor(client, url, data, status=200)

        assert 1 == int(discourse.client.sso_sync.called_count)

    def _update_account_field_discourse_down(
        self, discourse, client, settings, passwords, field, value
    ):
        discourse.down()

        url = '/users/account'
        currentpassword = passwords['contributor']

        data = {'currentpassword': currentpassword}
        data[field] = value
        post_json_with_contributor(client, url, data, status=500)

        assert 1 == int(discourse.client.sso_sync.called_count)

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_update_account_email_discourse_up(
        self, _send_email, client, session, user_ids, passwords, discourse
    ):
        new_email = 'superemail@localhost.localhost'
        self._update_account_field_discourse_up(
            discourse, client, passwords, 'email', new_email
        )

        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        assert user.email_to_validate == new_email
        assert user.email != new_email

        _send_email.assert_called_once()

        # Simulate confirmation email validation
        nonce = extract_nonce(_send_email, 'validate_change_email')
        url_api_validation = f'/users/validate_change_email/{nonce}'
        send_json(client, 'post', url_api_validation, {}, status=200)

        session.expunge(user)
        user = session.get(User, user_id)
        assert user.email == new_email
        assert user.validation_nonce is None

    def test_update_account_email_discourse_down(
        self, client, settings, passwords, discourse
    ):
        new_email = 'superemail@localhost.localhost'
        self._update_account_field_discourse_down(
            discourse, client, settings, passwords, 'email', new_email
        )

    def test_update_account_name_discourse_up(
        self, client, session, user_ids, passwords, queue_config, discourse
    ):
        self._update_account_field_discourse_up(
            discourse, client, passwords, 'name', 'changed'
        )

        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        assert user.name == 'changed'

        # check that the search index is updated with the new name
        sync_es_queue(session, queue_config)
        search_doc = search_documents[USERPROFILE_TYPE].get(
            id=user_id, index=elasticsearch_config['index']
        )

        # and check that the cache version of the user profile was updated
        # (from 2: creating the profile version of the test data bumped it)
        scenarios.check_cache_version(session, user_id, 3)

        assert search_doc['doc_type'] is not None
        assert search_doc['title_en'] == 'changed contributor'

    def test_update_account_name_discourse_down(
        self, client, settings, passwords, discourse
    ):
        self._update_account_field_discourse_down(
            discourse, client, settings, passwords, 'name', 'changed'
        )

    def test_update_account_forum_username_validity(self, client, passwords):
        url = '/users/account'
        i = 0
        for forum_username, value in forum_username_tests.items():
            i += 1
            body = {
                'currentpassword': passwords['contributor'],
                'forum_username': forum_username,
            }
            if value is False:
                post_json_with_contributor(client, url, body, status=200)
            else:
                # the schema checks it: 422
                json = post_json_with_contributor(client, url, body, status=422)
                assert errors_of(json)[0]['description'] == value

    def test_update_account_forum_username_unique(self, client, passwords):
        url = '/users/account'

        data = {
            'currentpassword': passwords['contributor'],
            'forum_username': 'unique',
        }
        post_json_with_contributor(client, url, data, status=200)

        data = {
            'currentpassword': passwords['contributor2'],
            'forum_username': 'Unique',
        }
        json = post_json_with_contributor(
            client, url, data, status=422, username='contributor2'
        )
        assert errors_of(json)[0]['description'] == 'Already used forum name'

    def test_update_account_forum_username_discourse_up(
        self, client, session, user_ids, passwords, discourse
    ):
        self._update_account_field_discourse_up(
            discourse, client, passwords, 'forum_username', 'changed'
        )

        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        assert user.forum_username == 'changed'

    def test_update_account_forum_username_discourse_down(
        self, client, settings, passwords, discourse
    ):
        self._update_account_field_discourse_down(
            discourse, client, settings, passwords, 'forum_username', 'changed'
        )

    def test_update_is_profile_public_discourse_down(
        self, client, session, user_ids, passwords
    ):
        data = {
            'currentpassword': passwords['contributor'],
            'is_profile_public': True,
        }
        post_json_with_contributor(client, '/users/account', data, status=200)

        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        assert user.is_profile_public is True

    def test_update_account_newpassword_too_weak(self, client, passwords):
        data = {
            'currentpassword': passwords['contributor'],
            'newpassword': 'alllowercase1',  # nosec - test fixture
        }
        body = post_json_with_contributor(client, '/users/account', data, status=422)
        assert_errors_contain(body, 'newpassword')

    def test_update_account_newpassword_success(
        self, client, session, user_ids, passwords
    ):
        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        initial_encoded_password = user.password

        data = {
            'currentpassword': passwords['contributor'],
            'newpassword': 'New$Password1',  # nosec - test fixture
        }
        post_json_with_contributor(client, '/users/account', data, status=200)

        session.expunge(user)
        user = session.get(User, user_id)
        assert initial_encoded_password != user.password

    def test_update_preferred_lang(self, client, session, user_ids):
        user_id = user_ids['contributor']
        user = session.get(User, user_id)
        assert user.lang == 'fr'

        request_body = {'lang': 'en'}
        url = PREFIX + '/update_preferred_language'
        post_json_with_contributor(client, url, request_body, status=200)

        session.expunge(user)
        user = session.get(User, user_id)
        assert user.lang == 'en'
