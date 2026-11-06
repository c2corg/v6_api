import pytest

from c2corg_api.tests import assert_notified_es, errors_of
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import writable

CREATE = ('POST', '/books')
UPDATE = ('PUT', '/books/{id}')

BOOK = {
    'book_types': ['biography'],
    'activities': ['hiking'],
    'locales': [{'lang': 'en', 'title': 'Another book'}],
}


def drain_es_notifications(queue_config):
    queue = queue_config.queue(queue_config.connection)
    while queue.get() is not None:
        pass


@pytest.mark.usefixtures('documents')
class TestBookWrites:
    """The answers of the book writes besides a creation and an update."""

    @contract(CREATE)
    def test_create_is_committed_and_synced(self, queue_config, browser):
        drain_es_notifications(queue_config)
        response = browser.post('/books', BOOK, user='contributor')
        check_snapshot('books_create_committed', response)
        book_id = response.json['document_id']
        # committed: the book can be read, and ElasticSearch is notified
        assert browser.get(f'/books/{book_id}').json['locales'][0]['title'] == (
            'Another book'
        )
        assert_notified_es(queue_config)

    @contract(CREATE)
    def test_create_invalid(self, browser):
        body = {'book_types': ['no such type'], 'locales': []}
        response = browser.post('/books', body, user='contributor', status=422)
        check_snapshot('books_create_invalid', response)
        assert [e['name'] for e in errors_of(response.json)] == ['book_types.0']

    @contract(CREATE)
    def test_create_refused(self, browser):
        check_snapshot(
            'books_create_anonymous',
            browser.post('/books', BOOK, status=403),
        )
        response = browser.request(
            'POST',
            '/books',
            user='contributor',
            headers={'Content-Type': 'text/plain'},
            params='{}',
            status=415,
        )
        check_snapshot('books_create_wrong_content_type', response)

    @contract(UPDATE)
    def test_update_with_an_old_version(self, documents):
        documents.retitle('books')

        def change(document):
            document['version'] -= 1

        response = documents.update('books', change, status=409)
        check_snapshot('books_update_conflict', response)

    @contract(UPDATE)
    def test_update_of_another_document(self, browser, documents):
        document = writable(browser.get(documents.url('books')).json)
        body = {'message': 'contract test', 'document': document}
        url = f'/books/{documents.ids["articles"]}'
        response = browser.put(url, body, user='contributor', status=400)
        check_snapshot('books_update_mismatch', response)
        assert response.json['errors'][0]['description'] == (
            'id in the url does not match document_id in request body'
        )
