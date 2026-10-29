from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import DocumentContractTest
from c2corg_api.tests.contract.test_users import UserContractTest


class TestForumTopicWrites(UserContractTest):
    @contract(('POST', '/forum/topics'))
    def test_refused(self):
        body = {'document_id': 9999999, 'lang': 'en'}
        response = self.post('/forum/topics', body, status=403)
        check_snapshot('forum_topics_anonymous', response)
        response = self.post('/forum/topics', body, user='contributor', status=400)
        check_snapshot('forum_topics_unknown_document', response)


class TestImageListWrites(DocumentContractTest):
    @contract(('POST', '/images/list'))
    def test_refused(self):
        response = self.post('/images/list', {'images': []}, status=403)
        check_snapshot('images_list_anonymous', response)
        response = self.post(
            '/images/list',
            {'images': [{'filename': 1}]},
            user='contributor',
            status=400,
        )
        check_snapshot('images_list_invalid', response)


class TestCookerAndCoverageWrites(DocumentContractTest):
    @contract(('POST', '/cooker'))
    def test_cooker(self):
        response = self.post('/cooker', {'lang': 'en', 'description': '**bold**'})
        check_snapshot('cooker', response)
        assert response.json == {
            'lang': 'en',
            'description': '<p><strong>bold</strong></p>',
        }
        response = self.post('/cooker', ['**bold**'], status=400)
        check_snapshot('cooker_not_an_object', response)

    @contract(('POST', '/getpolygoncoverage'))
    def test_invalid_polygon(self):
        response = self.post('/getpolygoncoverage', {}, status=400)
        check_snapshot('getpolygoncoverage_invalid', response)
