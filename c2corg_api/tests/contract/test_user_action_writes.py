from unittest.mock import patch

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_users import UserContractTest
from c2corg_api.tests.contract.test_writes import WriteContractTest


class TestAssociationWrites(WriteContractTest):
    @contract(('POST', '/associations'))
    def test_add_refused(self):
        association = {
            'parent_document_id': self.ids['waypoints'],
            'child_document_id': self.ids['routes'],
        }
        response = self.post('/associations', association, status=403)
        check_snapshot('associations_add_anonymous', response)
        unknown = {**association, 'child_document_id': 9999999}
        response = self.post('/associations', unknown, user='contributor', status=400)
        check_snapshot('associations_add_unknown', response)

    @contract(('DELETE', '/associations'))
    def test_remove_refused(self):
        # a contributor removes only the links to their own personal documents
        association = {
            'parent_document_id': self.ids['waypoints'],
            'child_document_id': self.ids['routes'],
        }
        response = self.request(
            'DELETE', '/associations', association, user='contributor', status=400
        )
        check_snapshot('associations_remove_refused', response)


class TestTagWrites(UserContractTest):
    @contract(('POST', '/tags/add'), ('POST', '/tags/remove'))
    def test_unknown_document(self):
        body = {'document_id': 9999999}
        for path in ('/tags/add', '/tags/remove'):
            response = self.post(path, body, user='contributor', status=400)
            check_snapshot('tags_unknown_document', response)


class TestFollowAndBlockWrites(UserContractTest):
    @contract(('POST', '/users/follow'), ('POST', '/users/unfollow'))
    def test_follow_unknown_user(self):
        for path in ('/users/follow', '/users/unfollow'):
            response = self.post(
                path, {'user_id': 9999999}, user='contributor', status=400
            )
            check_snapshot('users_follow_unknown', response)

    @contract(('POST', '/users/block'), ('POST', '/users/unblock'))
    def test_block_refused(self):
        body = {'user_id': self.global_userids['contributor2']}
        for path in ('/users/block', '/users/unblock'):
            response = self.post(path, body, user='contributor', status=403)
            check_snapshot('users_block_not_moderator', response)
            response = self.post(
                path, {'user_id': 9999999}, user='moderator', status=400
            )
            check_snapshot('users_block_unknown', response)


class TestPreferencesAndMailinglistsWrites(UserContractTest):
    @contract(('POST', '/users/preferences'))
    def test_invalid_preferences(self):
        body = {'followed_only': 'maybe', 'activities': ['flying'], 'langs': ['xx']}
        response = self.post('/users/preferences', body, user='contributor', status=400)
        check_snapshot('users_preferences_invalid', response)

    @contract(('POST', '/users/mailinglists'))
    def test_unknown_mailinglist(self):
        with patch('c2corg_api.emails.email_service.EmailService._send_email'):
            response = self.post(
                '/users/mailinglists',
                {'no-such-list': True},
                user='contributor',
                status=400,
            )
        check_snapshot('users_mailinglists_unknown', response)
