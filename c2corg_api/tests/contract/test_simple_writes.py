import pytest

from c2corg_api.tests import errors_of
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import writable


@pytest.mark.usefixtures('documents')
class TestArticleWrites:
    @contract(('PUT', '/articles/{id}'))
    def test_type_of_a_collaborative_article(self, documents):
        # only a moderator changes the type of a collaborative article
        def personal(document):
            document['article_type'] = 'personal'

        response = documents.update('articles', personal, status=400)
        check_snapshot('articles_update_type', response)
        assert response.json['errors'][0]['description'] == (
            'Article type cannot be changed for collaborative articles'
        )

    @contract(('POST', '/articles'), ('PUT', '/articles/{id}'))
    def test_personal_article_of_another_user(self, browser):
        body = {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'personal',
            'locales': [{'lang': 'en', 'title': 'My trip'}],
        }
        article_id = browser.post('/articles', body, user='contributor').json[
            'document_id'
        ]
        document = writable(browser.get(f'/articles/{article_id}').json)
        document['locales'][0]['title'] = 'Not my trip'
        body = {'message': 'contract test', 'document': document}
        response = browser.put(
            f'/articles/{article_id}',
            body,
            user='contributor2',
            status=403,
        )
        check_snapshot('articles_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this article'
        )

    @contract(('PUT', '/articles/{id}'))
    def test_unknown_article(self, browser, documents):
        document = writable(browser.get(documents.url('articles')).json)
        document['document_id'] = 9999999
        body = {'message': 'contract test', 'document': document}
        response = browser.put(
            '/articles/9999999', body, user='contributor', status=404
        )
        check_snapshot('articles_update_unknown', response)


@pytest.mark.usefixtures('documents')
class TestModeratedWrites:
    @contract(('POST', '/areas'))
    def test_create_area_needs_a_moderator(self, browser, documents):
        document = writable(browser.get(documents.url('areas')).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        response = browser.post('/areas', document, user='contributor', status=403)
        check_snapshot('areas_create_forbidden', response)

    @contract(('PUT', '/maps/{id}'))
    def test_update_map_needs_a_moderator(self, documents):
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = documents.update('maps', change, user='contributor', status=403)
        check_snapshot('maps_update_forbidden', response)


@pytest.mark.usefixtures('documents')
class TestCoverageWrites:
    @contract(('POST', '/coverages'))
    def test_create_invalid(self, browser):
        body = {'coverage_type': 'no-such-coverage', 'locales': []}
        response = browser.post('/coverages', body, user='contributor', status=422)
        check_snapshot('coverages_create_invalid', response)
        assert [e['name'] for e in errors_of(response.json)] == ['coverage_type']
