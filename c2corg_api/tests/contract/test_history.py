import pytest

from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract

HISTORY = ('GET', '/document/{id}/history/{lang}')
CHANGES = ('GET', '/documents/changes')
ASSOCIATIONS_HISTORY = ('GET', '/associations-history')


@pytest.mark.usefixtures('documents')
class TestDocumentHistory:
    @contract(HISTORY)
    def test_not_modified(self, browser, documents):
        url = f'/document/{documents.ids["waypoints"]}/history/en'
        etag = browser.get(url).headers['ETag']
        response = browser.get(url, headers={'If-None-Match': etag}, status=304)
        check_snapshot('history_not_modified', response)

    @contract(HISTORY)
    def test_missing_lang(self, browser, documents):
        # the waypoint has no French locale
        response = browser.get(
            f'/document/{documents.ids["waypoints"]}/history/fr',
            status=404,
        )
        check_snapshot('history_missing_lang', response)

    @contract(HISTORY)
    def test_unknown_document(self, browser):
        response = browser.get('/document/9999999/history/en', status=404)
        check_snapshot('history_unknown_document', response)

    @contract(HISTORY)
    def test_invalid_lang(self, browser, documents):
        response = browser.get(
            f'/document/{documents.ids["waypoints"]}/history/xx',
            status=422,
        )
        check_snapshot('history_invalid_lang', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['lang']


@pytest.mark.usefixtures('documents')
class TestDocumentChanges:
    @contract(CHANGES)
    def test_next_page_of_a_user(self, user_ids, browser):
        user_id = user_ids['contributor']
        first = browser.get('/documents/changes', params={'limit': 1, 'u': user_id})
        token = first.json['pagination_token']
        response = browser.get(
            '/documents/changes',
            params={'limit': 1, 'u': user_id, 'token': token},
        )
        check_snapshot('documents_changes_next_page', response)
        assert response.json['feed'][0]['user']['user_id'] == user_id

    @contract(CHANGES)
    def test_invalid_parameters(self, browser):
        # an invalid pagination token, not a password
        params = {'token': 'abc', 'u': 'x'}  # nosec B105
        response = browser.get('/documents/changes', params=params, status=422)
        check_snapshot('documents_changes_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['token', 'u']


@pytest.mark.usefixtures('documents')
class TestAssociationsHistory:
    @contract(ASSOCIATIONS_HISTORY)
    def test_of_a_user(self, user_ids, browser):
        user_id = user_ids['contributor']
        response = browser.get(
            '/associations-history',
            params={'u': user_id, 'offset': 1, 'limit': 2},
        )
        check_snapshot('associations_history_of_user', response)

    @contract(ASSOCIATIONS_HISTORY)
    def test_invalid_parameters(self, browser):
        response = browser.get('/associations-history', params={'d': 'abc'}, status=422)
        check_snapshot('associations_history_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['d']
