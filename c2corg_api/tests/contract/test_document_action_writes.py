import pytest

from c2corg_api.tests.contract import check_snapshot, contract

MODERATOR_ACTIONS = [
    ('/documents/merge', 'documents_merge'),
    ('/documents/protect', 'documents_protect'),
    ('/documents/unprotect', 'documents_unprotect'),
    ('/documents/revert', 'documents_revert'),
    ('/versions/mask', 'versions_mask'),
    ('/versions/unmask', 'versions_unmask'),
]


@pytest.mark.usefixtures('documents')
class TestDocumentActionWrites:
    def body(self, documents, path):
        waypoint = documents.ids['waypoints']
        if path == '/documents/merge':
            return {'source_document_id': waypoint, 'target_document_id': waypoint}
        if path in ('/documents/protect', '/documents/unprotect'):
            return {'document_id': waypoint}
        version = documents.history('waypoints')[0]
        return {'document_id': waypoint, 'lang': 'en', 'version_id': version}

    @contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
    def test_reserved_to_the_moderators(self, browser, documents):
        for path, _ in MODERATOR_ACTIONS:
            response = browser.post(
                path,
                self.body(documents, path),
                user='contributor',
                status=403,
            )
            check_snapshot('document_action_not_moderator', response)

    @contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
    def test_unknown_document(self, browser, documents):
        for path, name in MODERATOR_ACTIONS:
            body = self.body(documents, path)
            for key in ('document_id', 'source_document_id'):
                if key in body:
                    body[key] = 9999999
            response = browser.post(path, body, user='moderator', status=400)
            check_snapshot(f'{name}_unknown', response)

    @contract(('POST', '/documents/merge'))
    def test_merge_into_itself(self, browser, documents):
        response = browser.post(
            '/documents/merge',
            self.body(documents, '/documents/merge'),
            user='moderator',
            status=400,
        )
        check_snapshot('documents_merge_itself', response)

    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_unknown_document(self, browser):
        response = browser.request(
            'DELETE',
            '/documents/delete/9999999',
            {},
            user='moderator',
            status=404,
        )
        check_snapshot('documents_delete_unknown', response)

    @contract(('DELETE', '/documents/delete/{id}/{lang}'))
    def test_delete_locale_reserved_to_the_moderators(self, browser, documents):
        response = browser.request(
            'DELETE',
            f'/documents/delete/{documents.ids["waypoints"]}/en',
            {},
            user='contributor',
            status=403,
        )
        check_snapshot('documents_delete_locale_not_moderator', response)
