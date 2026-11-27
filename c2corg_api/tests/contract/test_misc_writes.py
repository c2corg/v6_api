import pytest

from c2corg_api.tests.contract import check_snapshot, contract


@pytest.mark.usefixtures('discourse')
class TestForumTopicWrites:
    @contract(('POST', '/forum/topics'))
    def test_refused(self, browser):
        body = {'document_id': 9999999, 'lang': 'en'}
        response = browser.post('/forum/topics', body, status=403)
        check_snapshot('forum_topics_anonymous', response)
        response = browser.post('/forum/topics', body, user='contributor', status=400)
        check_snapshot('forum_topics_unknown_document', response)


@pytest.mark.usefixtures('documents')
class TestImageListWrites:
    @contract(('POST', '/images/list'))
    def test_refused(self, browser):
        response = browser.post('/images/list', {'images': []}, status=403)
        check_snapshot('images_list_anonymous', response)
        response = browser.post(
            '/images/list',
            {'images': [{'filename': 1}]},
            user='contributor',
            status=422,
        )
        check_snapshot('images_list_invalid', response)


@pytest.mark.usefixtures('documents')
class TestCookerAndCoverageWrites:
    @contract(('POST', '/cooker'))
    def test_cooker(self, browser):
        response = browser.post('/cooker', {'lang': 'en', 'description': '**bold**'})
        check_snapshot('cooker', response)
        assert response.json == {
            'lang': 'en',
            'description': '<p><strong>bold</strong></p>',
        }
        response = browser.post('/cooker', ['**bold**'], status=400)
        check_snapshot('cooker_not_an_object', response)

    @contract(('POST', '/getpolygoncoverage'))
    def test_invalid_polygon(self, browser):
        response = browser.post('/getpolygoncoverage', {}, status=400)
        check_snapshot('getpolygoncoverage_invalid', response)
