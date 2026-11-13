from unittest.mock import Mock, patch

import pytest

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.documents import (
    MODERATED_TYPES,
    writable,
)
from c2corg_api.tests.contract.test_documents import (
    DOCUMENT_TYPES,
    POINT,
    _routes,
)

# the types the documents fixture creates (profiles come with users)
CREATED_TYPES = [t for t in DOCUMENT_TYPES if t != 'profiles']


@pytest.fixture(autouse=True)
def image_backend():
    """Fake the image backend that image creation and deletion call."""
    with patch(
        'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
    ) as post:
        yield post


@pytest.mark.usefixtures('documents')
class TestDocumentCreate:
    @contract(*_routes('POST', '/{prefix}', CREATED_TYPES))
    @pytest.mark.parametrize('prefix', CREATED_TYPES)
    def test_create(self, prefix, browser, documents):
        # the documents fixture created them: create a second one the same way
        document = writable(browser.get(documents.url(prefix)).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        if prefix == 'images':
            document['filename'] = 'image2.jpg'
        user = 'moderator' if prefix in MODERATED_TYPES else 'contributor'
        response = browser.post(f'/{prefix}', document, user=user)
        check_snapshot(f'{prefix}_create', response)

    @contract(('POST', '/waypoints'))
    def test_create_anonymous(self, browser):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Anonymous'}],
        }
        check_snapshot(
            'waypoints_create_anonymous',
            browser.post('/waypoints', body, status=403),
        )


@pytest.mark.usefixtures('documents')
class TestDocumentUpdate:
    @contract(*_routes('PUT', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_update(self, prefix, documents):
        response = documents.retitle(prefix)
        check_snapshot(f'{prefix}_update', response)

    @contract(('PUT', '/waypoints/{id}'))
    def test_update_with_an_old_version(self, documents):
        documents.retitle('waypoints')

        def change(document):
            document['version'] -= 1

        response = documents.update('waypoints', change, status=409)
        check_snapshot('waypoints_update_conflict', response)


@pytest.mark.usefixtures('documents')
class TestDocumentModeration:
    @contract(('POST', '/documents/protect'), ('POST', '/documents/unprotect'))
    def test_protect_and_unprotect(self, browser, documents):
        body = {'document_id': documents.ids['waypoints']}
        protect = browser.post('/documents/protect', body, user='moderator')
        check_snapshot('documents_protect', protect)
        assert browser.get(documents.url('waypoints')).json['protected'] is True
        unprotect = browser.post('/documents/unprotect', body, user='moderator')
        check_snapshot('documents_unprotect', unprotect)
        assert browser.get(documents.url('waypoints')).json['protected'] is False

    @contract(('POST', '/documents/revert'))
    def test_revert(self, browser, documents):
        documents.retitle('waypoints')
        first = documents.history('waypoints')[0]
        body = {
            'document_id': documents.ids['waypoints'],
            'lang': 'en',
            'version_id': first,
        }
        check_snapshot(
            'documents_revert',
            browser.post('/documents/revert', body, user='moderator'),
        )
        assert (
            browser.get(documents.url('waypoints')).json['locales'][0]['title']
            == 'Mont Pourri'
        )

    @contract(('POST', '/versions/mask'), ('POST', '/versions/unmask'))
    def test_mask_and_unmask(self, browser, documents):
        documents.retitle('waypoints')
        first = documents.history('waypoints')[0]
        body = {
            'document_id': documents.ids['waypoints'],
            'lang': 'en',
            'version_id': first,
        }
        check_snapshot(
            'versions_mask',
            browser.post('/versions/mask', body, user='moderator'),
        )
        check_snapshot(
            'waypoints_version_masked',
            browser.get(documents.url('waypoints', f'/en/{first}')),
        )
        check_snapshot(
            'versions_unmask',
            browser.post('/versions/unmask', body, user='moderator'),
        )

    @contract(('POST', '/documents/merge'))
    def test_merge(self, browser, documents):
        source = browser.create(
            'articles',
            {
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [{'lang': 'en', 'title': 'Duplicate'}],
            },
        )
        body = {
            'source_document_id': source,
            'target_document_id': documents.ids['articles'],
        }
        check_snapshot(
            'documents_merge',
            browser.post('/documents/merge', body, user='moderator'),
        )
        # the source now redirects to the target
        redirect = browser.get(f'/articles/{source}').json
        assert redirect['redirects_to'] == documents.ids['articles']


@pytest.mark.usefixtures('documents')
class TestDocumentDelete:
    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_own_outing(self, browser, documents):
        response = browser.request(
            'DELETE',
            f'/documents/delete/{documents.ids["outings"]}',
            user='contributor',
        )
        check_snapshot('documents_delete', response)
        browser.get(documents.url('outings'), status=404)

    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_refused(self, browser, documents):
        response = browser.request(
            'DELETE',
            f'/documents/delete/{documents.ids["waypoints"]}',
            user='contributor',
            status=400,
        )
        check_snapshot('documents_delete_refused', response)

    @contract(('DELETE', '/documents/delete/{id}/{lang}'))
    def test_delete_locale(self, browser, documents):
        # a translation added in its own version (#2406)
        def add_french(document):
            document['locales'].append({'lang': 'fr', 'title': 'Rapport'})

        documents.update('xreports', add_french)
        response = browser.request(
            'DELETE',
            f'/documents/delete/{documents.ids["xreports"]}/fr',
            user='moderator',
        )
        check_snapshot('documents_delete_locale', response)
        langs = browser.get(documents.url('xreports'), user='moderator').json[
            'available_langs'
        ]
        assert langs == ['en']


@pytest.fixture
def association(browser, documents):
    """Create a waypoint; return its link to the route, as a write takes it."""
    child = browser.create(
        'waypoints',
        {
            'waypoint_type': 'access',
            'elevation': 1200,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Car park'}],
        },
    )
    # a contributor may link a waypoint to a route
    return {'parent_document_id': child, 'child_document_id': documents.ids['routes']}


@pytest.mark.usefixtures('association')
class TestAssociations:
    @contract(('POST', '/associations'), ('DELETE', '/associations'))
    def test_add_and_remove(self, browser, association):
        added = browser.post('/associations', association, user='contributor')
        check_snapshot('associations_add', added)
        # a contributor may only remove links to their own personal documents
        removed = browser.request(
            'DELETE',
            '/associations',
            association,
            user='moderator',
        )
        check_snapshot('associations_remove', removed)

    @contract(('GET', '/associations-history'))
    def test_history(self, browser, association):
        browser.post('/associations', association, user='contributor')
        response = browser.get(
            '/associations-history', params={'d': association['parent_document_id']}
        )
        check_snapshot('associations_history', response)
        assert response.json['count'] >= 1

    @contract(('GET', '/documents/changes'))
    def test_changes(self, browser):
        response = browser.get('/documents/changes', params={'limit': 5})
        check_snapshot('documents_changes', response)
