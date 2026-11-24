import pytest

from c2corg_api.tests.contract import check_snapshot, contract

pytestmark = pytest.mark.usefixtures('documents')

MODERATOR_ACTIONS = [
    ('/documents/merge', 'documents_merge'),
    ('/documents/protect', 'documents_protect'),
    ('/documents/unprotect', 'documents_unprotect'),
    ('/documents/revert', 'documents_revert'),
    ('/versions/mask', 'versions_mask'),
    ('/versions/unmask', 'versions_unmask'),
]


def request_body(documents, path):
    waypoint = documents.ids['waypoints']
    if path == '/documents/merge':
        return {'source_document_id': waypoint, 'target_document_id': waypoint}
    if path in ('/documents/protect', '/documents/unprotect'):
        return {'document_id': waypoint}
    version = documents.history('waypoints')[0]
    return {'document_id': waypoint, 'lang': 'en', 'version_id': version}


@contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
def test_reserved_to_the_moderators(browser, documents):
    for path, _ in MODERATOR_ACTIONS:
        response = browser.post(
            path,
            request_body(documents, path),
            user='contributor',
            status=403,
        )
        check_snapshot('document_action_not_moderator', response)


@contract(*[('POST', path) for path, _ in MODERATOR_ACTIONS])
def test_unknown_document(browser, documents):
    for path, name in MODERATOR_ACTIONS:
        body = request_body(documents, path)
        for key in ('document_id', 'source_document_id'):
            if key in body:
                body[key] = 9999999
        response = browser.post(path, body, user='moderator', status=400)
        check_snapshot(f'{name}_unknown', response)


@contract(('POST', '/documents/merge'))
def test_merge_into_itself(browser, documents):
    response = browser.post(
        '/documents/merge',
        request_body(documents, '/documents/merge'),
        user='moderator',
        status=400,
    )
    check_snapshot('documents_merge_itself', response)


@contract(('DELETE', '/documents/delete/{id}'))
def test_delete_unknown_document(browser):
    response = browser.request(
        'DELETE',
        '/documents/delete/9999999',
        {},
        user='moderator',
        status=404,
    )
    check_snapshot('documents_delete_unknown', response)


@contract(('DELETE', '/documents/delete/{id}/{lang}'))
def test_delete_locale_reserved_to_the_moderators(browser, documents):
    response = browser.request(
        'DELETE',
        f'/documents/delete/{documents.ids["waypoints"]}/en',
        {},
        user='contributor',
        status=403,
    )
    check_snapshot('documents_delete_locale_not_moderator', response)


DELETED_DOCUMENT_ROUTES = [
    ('GET', '/documents/deleted'),
    ('GET', '/documents/deleted/{id}'),
    ('POST', '/documents/deleted/{id}/restore'),
    ('GET', '/images/orphans'),
    ('GET', '/images/broken-embeds'),
]


@contract(*DELETED_DOCUMENT_ROUTES)
def test_deleted_documents_reserved_to_the_moderators(browser):
    for method, path in DELETED_DOCUMENT_ROUTES:
        url = path.replace('{id}', '1')
        if method == 'GET':
            response = browser.get(url, user='contributor', status=403)
        else:
            response = browser.post(url, {}, user='contributor', status=403)
        check_snapshot('document_action_not_moderator', response)


@contract(('GET', '/documents/deleted'))
def test_deleted_documents(browser):
    response = browser.get('/documents/deleted', user='moderator')
    check_snapshot('documents_deleted', response)


@contract(('GET', '/documents/delete/{id}/images'))
def test_images_of_deletion_unknown(browser):
    response = browser.get(
        '/documents/delete/9999999/images', user='moderator', status=404
    )
    check_snapshot('documents_delete_images_unknown', response)


@contract(('GET', '/images/orphans'))
def test_orphan_images(browser):
    response = browser.get('/images/orphans', user='moderator')
    check_snapshot('images_orphans', response)


@contract(('GET', '/images/broken-embeds'))
def test_broken_embeds(browser):
    response = browser.get('/images/broken-embeds', user='moderator')
    check_snapshot('images_broken_embeds', response)


@contract(
    ('GET', '/documents/deleted/{id}'), ('POST', '/documents/deleted/{id}/restore')
)
def test_deleted_document_unknown(browser):
    url = '/documents/deleted/9999999'
    response = browser.get(url, user='moderator', status=404)
    check_snapshot('documents_deleted_unknown_get', response)
    response = browser.post(f'{url}/restore', {}, user='moderator', status=404)
    check_snapshot('documents_deleted_unknown_restore', response)
