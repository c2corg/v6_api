from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import WriteContractTest

MODERATOR_ACTIONS = [
    ('/documents/merge', 'documents_merge'),
    ('/documents/protect', 'documents_protect'),
    ('/documents/unprotect', 'documents_unprotect'),
    ('/documents/revert', 'documents_revert'),
    ('/versions/mask', 'versions_mask'),
    ('/versions/unmask', 'versions_unmask'),
]


class TestDocumentActionWrites(WriteContractTest):
    def body(self, client, settings, path):
        waypoint = self.ids['waypoints']
        if path == '/documents/merge':
            return {'source_document_id': waypoint, 'target_document_id': waypoint}
        if path in ('/documents/protect', '/documents/unprotect'):
            return {'document_id': waypoint}
        version = self.history(client, settings, 'waypoints')[0]
        return {'document_id': waypoint, 'lang': 'en', 'version_id': version}

    @contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
    def test_reserved_to_the_moderators(self, client, settings):
        for path, _ in MODERATOR_ACTIONS:
            response = self.post(
                client,
                settings,
                path,
                self.body(client, settings, path),
                user='contributor',
                status=403,
            )
            check_snapshot('document_action_not_moderator', response)

    @contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
    def test_unknown_document(self, client, settings):
        for path, name in MODERATOR_ACTIONS:
            body = self.body(client, settings, path)
            for key in ('document_id', 'source_document_id'):
                if key in body:
                    body[key] = 9999999
            response = self.post(
                client, settings, path, body, user='moderator', status=400
            )
            check_snapshot(f'{name}_unknown', response)

    @contract(('POST', '/documents/merge'))
    def test_merge_into_itself(self, client, settings):
        response = self.post(
            client,
            settings,
            '/documents/merge',
            self.body(client, settings, '/documents/merge'),
            user='moderator',
            status=400,
        )
        check_snapshot('documents_merge_itself', response)

    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_unknown_document(self, client, settings):
        response = self.request(
            client,
            settings,
            'DELETE',
            '/documents/delete/9999999',
            {},
            user='moderator',
            status=404,
        )
        check_snapshot('documents_delete_unknown', response)

    @contract(('DELETE', '/documents/delete/{id}/{lang}'))
    def test_delete_locale_reserved_to_the_moderators(self, client, settings):
        response = self.request(
            client,
            settings,
            'DELETE',
            f'/documents/delete/{self.ids["waypoints"]}/en',
            {},
            user='contributor',
            status=403,
        )
        check_snapshot('documents_delete_locale_not_moderator', response)
