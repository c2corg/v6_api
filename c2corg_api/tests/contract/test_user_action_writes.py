from unittest.mock import patch

import pytest

from c2corg_api.tests.contract import check_snapshot, contract


@pytest.mark.usefixtures('documents')
class TestAssociationWrites:
    @contract(('POST', '/associations'))
    def test_add_refused(self, browser, documents):
        association = {
            'parent_document_id': documents.ids['waypoints'],
            'child_document_id': documents.ids['routes'],
        }
        response = browser.post('/associations', association, status=403)
        check_snapshot('associations_add_anonymous', response)
        unknown = {**association, 'child_document_id': 9999999}
        response = browser.post(
            '/associations', unknown, user='contributor', status=400
        )
        check_snapshot('associations_add_unknown', response)

    @contract(('DELETE', '/associations'))
    def test_remove_refused(self, browser, documents):
        # a contributor removes only the links to their own personal documents
        association = {
            'parent_document_id': documents.ids['waypoints'],
            'child_document_id': documents.ids['routes'],
        }
        response = browser.request(
            'DELETE',
            '/associations',
            association,
            user='contributor',
            status=400,
        )
        check_snapshot('associations_remove_refused', response)


@pytest.mark.usefixtures('discourse')
class TestTagWrites:
    @contract(('POST', '/tags/add'), ('POST', '/tags/remove'))
    def test_unknown_document(self, browser):
        body = {'document_id': 9999999}
        for path in ('/tags/add', '/tags/remove'):
            response = browser.post(path, body, user='contributor', status=400)
            check_snapshot('tags_unknown_document', response)


@pytest.mark.usefixtures('discourse')
class TestFollowAndBlockWrites:
    @contract(('POST', '/users/follow'), ('POST', '/users/unfollow'))
    def test_follow_unknown_user(self, browser):
        for path in ('/users/follow', '/users/unfollow'):
            response = browser.post(
                path,
                {'user_id': 9999999},
                user='contributor',
                status=400,
            )
            check_snapshot('users_follow_unknown', response)

    @contract(('POST', '/users/block'), ('POST', '/users/unblock'))
    def test_block_refused(self, user_ids, browser):
        body = {'user_id': user_ids['contributor2']}
        for path in ('/users/block', '/users/unblock'):
            response = browser.post(path, body, user='contributor', status=403)
            check_snapshot('users_block_not_moderator', response)
            response = browser.post(
                path,
                {'user_id': 9999999},
                user='moderator',
                status=400,
            )
            check_snapshot('users_block_unknown', response)


@pytest.mark.usefixtures('discourse')
class TestPreferencesAndMailinglistsWrites:
    @contract(('POST', '/users/preferences'))
    def test_invalid_preferences(self, browser):
        body = {'followed_only': 'maybe', 'activities': ['flying'], 'langs': ['xx']}
        response = browser.post(
            '/users/preferences', body, user='contributor', status=422
        )
        check_snapshot('users_preferences_invalid', response)

    @contract(('POST', '/users/mailinglists'))
    def test_unknown_mailinglist(self, browser):
        with patch('c2corg_api.emails.email_service.EmailService._send_email'):
            response = browser.post(
                '/users/mailinglists',
                {'no-such-list': True},
                user='contributor',
                status=400,
            )
        check_snapshot('users_mailinglists_unknown', response)
