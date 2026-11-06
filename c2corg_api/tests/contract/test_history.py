from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import DocumentContractTest

HISTORY = ('GET', '/document/{id}/history/{lang}')
CHANGES = ('GET', '/documents/changes')
ASSOCIATIONS_HISTORY = ('GET', '/associations-history')


class TestDocumentHistory(DocumentContractTest):
    @contract(HISTORY)
    def test_not_modified(self, client, settings):
        url = f'/document/{self.ids["waypoints"]}/history/en'
        etag = self.get(client, settings, url).headers['ETag']
        response = self.get(
            client, settings, url, headers={'If-None-Match': etag}, status=304
        )
        check_snapshot('history_not_modified', response)

    @contract(HISTORY)
    def test_missing_lang(self, client, settings):
        # the waypoint has no French locale
        response = self.get(
            client,
            settings,
            f'/document/{self.ids["waypoints"]}/history/fr',
            status=404,
        )
        check_snapshot('history_missing_lang', response)

    @contract(HISTORY)
    def test_unknown_document(self, client, settings):
        response = self.get(
            client, settings, '/document/9999999/history/en', status=404
        )
        check_snapshot('history_unknown_document', response)

    @contract(HISTORY)
    def test_invalid_lang(self, client, settings):
        response = self.get(
            client,
            settings,
            f'/document/{self.ids["waypoints"]}/history/xx',
            status=422,
        )
        check_snapshot('history_invalid_lang', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['lang']


class TestDocumentChanges(DocumentContractTest):
    @contract(CHANGES)
    def test_next_page_of_a_user(self, client, settings, user_ids):
        user_id = user_ids['contributor']
        first = self.get(
            client, settings, '/documents/changes', params={'limit': 1, 'u': user_id}
        )
        token = first.json['pagination_token']
        response = self.get(
            client,
            settings,
            '/documents/changes',
            params={'limit': 1, 'u': user_id, 'token': token},
        )
        check_snapshot('documents_changes_next_page', response)
        assert response.json['feed'][0]['user']['user_id'] == user_id

    @contract(CHANGES)
    def test_invalid_parameters(self, client, settings):
        # an invalid pagination token, not a password
        params = {'token': 'abc', 'u': 'x'}  # nosec B105
        response = self.get(
            client, settings, '/documents/changes', params=params, status=422
        )
        check_snapshot('documents_changes_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['token', 'u']


class TestAssociationsHistory(DocumentContractTest):
    @contract(ASSOCIATIONS_HISTORY)
    def test_of_a_user(self, client, settings, user_ids):
        user_id = user_ids['contributor']
        response = self.get(
            client,
            settings,
            '/associations-history',
            params={'u': user_id, 'offset': 1, 'limit': 2},
        )
        check_snapshot('associations_history_of_user', response)

    @contract(ASSOCIATIONS_HISTORY)
    def test_invalid_parameters(self, client, settings):
        response = self.get(
            client, settings, '/associations-history', params={'d': 'abc'}, status=422
        )
        check_snapshot('associations_history_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['d']
