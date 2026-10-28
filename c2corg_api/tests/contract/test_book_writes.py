from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import WriteContractTest, writable

CREATE = ('POST', '/books')
UPDATE = ('PUT', '/books/{id}')

BOOK = {
    'book_types': ['biography'],
    'activities': ['hiking'],
    'locales': [{'lang': 'en', 'title': 'Another book'}],
}


class TestBookWrites(WriteContractTest):
    """The answers of the book writes besides a creation and an update."""

    def drain_es_notifications(self):
        queue = self.queue_config.queue(self.queue_config.connection)
        while queue.get() is not None:
            pass

    @contract(CREATE)
    def test_create_is_committed_and_synced(self):
        self.drain_es_notifications()
        response = self.post('/books', BOOK, user='contributor')
        check_snapshot('books_create_committed', response)
        book_id = response.json['document_id']
        # committed: the book can be read, and ElasticSearch is notified
        assert self.get(f'/books/{book_id}').json['locales'][0]['title'] == (
            'Another book'
        )
        self.assertNotifiedEs()

    @contract(CREATE)
    def test_create_invalid(self):
        body = {'book_types': ['no such type'], 'locales': []}
        response = self.post('/books', body, user='contributor', status=400)
        check_snapshot('books_create_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['book_types.0']

    @contract(CREATE)
    def test_create_refused(self):
        check_snapshot('books_create_anonymous', self.post('/books', BOOK, status=403))
        response = self.request(
            'POST',
            '/books',
            user='contributor',
            headers={'Content-Type': 'text/plain'},
            params='{}',
            status=415,
        )
        check_snapshot('books_create_wrong_content_type', response)

    @contract(UPDATE)
    def test_update_with_an_old_version(self):
        self.retitle('books')

        def change(document):
            document['version'] -= 1

        response = self.update('books', change, status=409)
        check_snapshot('books_update_conflict', response)

    @contract(UPDATE)
    def test_update_of_another_document(self):
        document = writable(self.get(self.url('books')).json)
        body = {'message': 'contract test', 'document': document}
        url = f'/books/{self.ids["articles"]}'
        response = self.put(url, body, user='contributor', status=400)
        check_snapshot('books_update_mismatch', response)
        assert response.json['errors'][0]['description'] == (
            'id in the url does not match document_id in request body'
        )
