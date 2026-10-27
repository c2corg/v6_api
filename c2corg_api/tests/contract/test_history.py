from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import DocumentContractTest

HISTORY = ('GET', '/document/{id}/history/{lang}')
CHANGES = ('GET', '/documents/changes')
ASSOCIATIONS_HISTORY = ('GET', '/associations-history')


class TestDocumentHistory(DocumentContractTest):
    @contract(HISTORY)
    def test_not_modified(self):
        url = f'/document/{self.ids["waypoints"]}/history/en'
        etag = self.get(url).headers['ETag']
        response = self.get(url, headers={'If-None-Match': etag}, status=304)
        check_snapshot('history_not_modified', response)

    @contract(HISTORY)
    def test_missing_lang(self):
        # the waypoint has no French locale
        response = self.get(f'/document/{self.ids["waypoints"]}/history/fr', status=404)
        check_snapshot('history_missing_lang', response)

    @contract(HISTORY)
    def test_unknown_document(self):
        response = self.get('/document/9999999/history/en', status=404)
        check_snapshot('history_unknown_document', response)

    @contract(HISTORY)
    def test_invalid_lang(self):
        response = self.get(f'/document/{self.ids["waypoints"]}/history/xx', status=400)
        check_snapshot('history_invalid_lang', response)
        assert [e['name'] for e in response.json['errors']] == ['lang']


class TestDocumentChanges(DocumentContractTest):
    @contract(CHANGES)
    def test_next_page_of_a_user(self):
        user_id = self.global_userids['contributor']
        first = self.get('/documents/changes', params={'limit': 1, 'u': user_id})
        token = first.json['pagination_token']
        response = self.get(
            '/documents/changes', params={'limit': 1, 'u': user_id, 'token': token}
        )
        check_snapshot('documents_changes_next_page', response)
        assert response.json['feed'][0]['user']['user_id'] == user_id

    @contract(CHANGES)
    def test_invalid_parameters(self):
        response = self.get(
            '/documents/changes', params={'token': 'abc', 'u': 'x'}, status=400
        )
        check_snapshot('documents_changes_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['token', 'u']


class TestAssociationsHistory(DocumentContractTest):
    @contract(ASSOCIATIONS_HISTORY)
    def test_of_a_user(self):
        user_id = self.global_userids['contributor']
        response = self.get(
            '/associations-history', params={'u': user_id, 'offset': 1, 'limit': 2}
        )
        check_snapshot('associations_history_of_user', response)

    @contract(ASSOCIATIONS_HISTORY)
    def test_invalid_parameters(self):
        response = self.get('/associations-history', params={'d': 'abc'}, status=400)
        check_snapshot('associations_history_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['d']
