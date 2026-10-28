from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import WriteContractTest, writable


class TestArticleWrites(WriteContractTest):
    @contract(('PUT', '/articles/{id}'))
    def test_type_of_a_collaborative_article(self):
        # only a moderator changes the type of a collaborative article
        def personal(document):
            document['article_type'] = 'personal'

        response = self.update('articles', personal, status=400)
        check_snapshot('articles_update_type', response)
        assert response.json['errors'][0]['description'] == (
            'Article type cannot be changed for collaborative articles'
        )

    @contract(('POST', '/articles'), ('PUT', '/articles/{id}'))
    def test_personal_article_of_another_user(self):
        body = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'personal',
            'locales': [{'lang': 'en', 'title': 'My trip'}],
        }
        article_id = self.post('/articles', body, user='contributor').json[
            'document_id'
        ]
        document = writable(self.get(f'/articles/{article_id}').json)
        document['locales'][0]['title'] = 'Not my trip'
        body = {'message': 'contract test', 'document': document}
        response = self.put(
            f'/articles/{article_id}', body, user='contributor2', status=403
        )
        check_snapshot('articles_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this article'
        )

    @contract(('PUT', '/articles/{id}'))
    def test_unknown_article(self):
        document = writable(self.get(self.url('articles')).json)
        document['document_id'] = 9999999
        body = {'message': 'contract test', 'document': document}
        response = self.put('/articles/9999999', body, user='contributor', status=404)
        check_snapshot('articles_update_unknown', response)


class TestModeratedWrites(WriteContractTest):
    @contract(('POST', '/areas'))
    def test_create_area_needs_a_moderator(self):
        document = writable(self.get(self.url('areas')).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        response = self.post('/areas', document, user='contributor', status=403)
        check_snapshot('areas_create_forbidden', response)

    @contract(('PUT', '/maps/{id}'))
    def test_update_map_needs_a_moderator(self):
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = self.update('maps', change, user='contributor', status=403)
        check_snapshot('maps_update_forbidden', response)


class TestCoverageWrites(WriteContractTest):
    @contract(('POST', '/coverages'))
    def test_create_invalid(self):
        body = {'coverage_type': 'no-such-coverage', 'locales': []}
        response = self.post('/coverages', body, user='contributor', status=400)
        check_snapshot('coverages_create_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['coverage_type']
