from unittest.mock import Mock, patch

import pytest

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import (
    DOCUMENT_TYPES,
    POINT,
    DocumentContractTest,
    _routes,
)

# the types created in DocumentContractTest.setUp (profiles come with users)
CREATED_TYPES = [t for t in DOCUMENT_TYPES if t != 'profiles']
# only moderators may change these
MODERATED_TYPES = ('areas', 'maps')

# what a GET returns but a POST or PUT does not take
READ_ONLY_FIELDS = ('areas', 'maps', 'available_langs', 'cooked')


def writable(document, keep_ids=True):
    """Turn a document as GET returns it into a POST or PUT body."""
    for field in READ_ONLY_FIELDS:
        document.pop(field, None)
    if not keep_ids:
        document.pop('document_id', None)
        document.pop('version', None)
    # GET returns the associated documents, a write takes their ids
    associations = document.pop('associations', None) or {}
    document['associations'] = {
        kind: [{'document_id': d['document_id']} for d in docs]
        for kind, docs in associations.items()
        if isinstance(docs, list)
    }
    return document


@pytest.fixture(autouse=True)
def image_backend():
    """Fake the image backend that image creation and deletion call."""
    with patch(
        'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
    ) as post:
        yield post


class WriteContractTest(DocumentContractTest):
    def update(self, prefix, change, user='contributor', status=200):
        """Change a document through the API and return the response."""
        document = writable(self.get(self.url(prefix), user=user).json)
        change(document)
        body = {'message': 'contract test', 'document': document}
        return self.put(self.url(prefix), body, user=user, status=status)

    def history(self, prefix, lang='en'):
        """Return the version ids of a document, oldest first."""
        versions = self.get(f'/document/{self.ids[prefix]}/history/{lang}').json
        return sorted(v['version_id'] for v in versions['versions'])

    def retitle(self, prefix):
        def change(document):
            # profiles have no title
            field = 'description' if prefix == 'profiles' else 'title'
            locale = document['locales'][0]
            locale[field] = (locale.get(field) or '') + ' (2)'

        user = 'moderator' if prefix in MODERATED_TYPES else 'contributor'
        return self.update(prefix, change, user=user)


class TestDocumentCreate(WriteContractTest):
    @contract(*_routes('POST', '/{prefix}', CREATED_TYPES))
    @pytest.mark.parametrize('prefix', CREATED_TYPES)
    def test_create(self, prefix):
        # setUp created the documents: create a second one the same way
        document = writable(self.get(self.url(prefix)).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        if prefix == 'images':
            document['filename'] = 'image2.jpg'
        user = 'moderator' if prefix in MODERATED_TYPES else 'contributor'
        response = self.post(f'/{prefix}', document, user=user)
        check_snapshot(f'{prefix}_create', response)

    @contract(('POST', '/waypoints'))
    def test_create_anonymous(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Anonymous'}],
        }
        check_snapshot(
            'waypoints_create_anonymous', self.post('/waypoints', body, status=403)
        )


class TestDocumentUpdate(WriteContractTest):
    @contract(*_routes('PUT', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_update(self, prefix):
        response = self.retitle(prefix)
        check_snapshot(f'{prefix}_update', response)

    @contract(('PUT', '/waypoints/{id}'))
    def test_update_with_an_old_version(self):
        self.retitle('waypoints')

        def change(document):
            document['version'] -= 1

        response = self.update('waypoints', change, status=409)
        check_snapshot('waypoints_update_conflict', response)


class TestDocumentModeration(WriteContractTest):
    @contract(('POST', '/documents/protect'), ('POST', '/documents/unprotect'))
    def test_protect_and_unprotect(self):
        body = {'document_id': self.ids['waypoints']}
        protect = self.post('/documents/protect', body, user='moderator')
        check_snapshot('documents_protect', protect)
        assert self.get(self.url('waypoints')).json['protected'] is True
        unprotect = self.post('/documents/unprotect', body, user='moderator')
        check_snapshot('documents_unprotect', unprotect)
        assert self.get(self.url('waypoints')).json['protected'] is False

    @contract(('POST', '/documents/revert'))
    def test_revert(self):
        self.retitle('waypoints')
        first = self.history('waypoints')[0]
        body = {'document_id': self.ids['waypoints'], 'lang': 'en', 'version_id': first}
        check_snapshot(
            'documents_revert', self.post('/documents/revert', body, user='moderator')
        )
        assert (
            self.get(self.url('waypoints')).json['locales'][0]['title'] == 'Mont Pourri'
        )

    @contract(('POST', '/versions/mask'), ('POST', '/versions/unmask'))
    def test_mask_and_unmask(self):
        self.retitle('waypoints')
        first = self.history('waypoints')[0]
        body = {'document_id': self.ids['waypoints'], 'lang': 'en', 'version_id': first}
        check_snapshot(
            'versions_mask', self.post('/versions/mask', body, user='moderator')
        )
        check_snapshot(
            'waypoints_version_masked',
            self.get(self.url('waypoints', f'/en/{first}')),
        )
        check_snapshot(
            'versions_unmask', self.post('/versions/unmask', body, user='moderator')
        )

    @contract(('POST', '/documents/merge'))
    def test_merge(self):
        source = self.create(
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
            'target_document_id': self.ids['articles'],
        }
        check_snapshot(
            'documents_merge', self.post('/documents/merge', body, user='moderator')
        )
        # the source now redirects to the target
        redirect = self.get(f'/articles/{source}').json
        assert redirect['redirects_to'] == self.ids['articles']


class TestDocumentDelete(WriteContractTest):
    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_own_outing(self):
        response = self.request(
            'DELETE', f'/documents/delete/{self.ids["outings"]}', user='contributor'
        )
        check_snapshot('documents_delete', response)
        self.get(self.url('outings'), status=404)

    @contract(('DELETE', '/documents/delete/{id}'))
    def test_delete_refused(self):
        response = self.request(
            'DELETE',
            f'/documents/delete/{self.ids["waypoints"]}',
            user='contributor',
            status=400,
        )
        check_snapshot('documents_delete_refused', response)

    @contract(('DELETE', '/documents/delete/{id}/{lang}'))
    def test_delete_locale(self):
        # a translation added in its own version (#2406)
        def add_french(document):
            document['locales'].append({'lang': 'fr', 'title': 'Rapport'})

        self.update('xreports', add_french)
        response = self.request(
            'DELETE', f'/documents/delete/{self.ids["xreports"]}/fr', user='moderator'
        )
        check_snapshot('documents_delete_locale', response)
        langs = self.get(self.url('xreports'), user='moderator').json['available_langs']
        assert langs == ['en']


class TestAssociations(WriteContractTest):
    def setUp(self):
        super().setUp()
        self.child = self.create(
            'waypoints',
            {
                'waypoint_type': 'access',
                'elevation': 1200,
                'geometry': {'geom': POINT},
                'locales': [{'lang': 'en', 'title': 'Car park'}],
            },
        )
        # a contributor may link a waypoint to a route
        self.association = {
            'parent_document_id': self.child,
            'child_document_id': self.ids['routes'],
        }

    @contract(('POST', '/associations'), ('DELETE', '/associations'))
    def test_add_and_remove(self):
        added = self.post('/associations', self.association, user='contributor')
        check_snapshot('associations_add', added)
        # a contributor may only remove links to their own personal documents
        removed = self.request(
            'DELETE', '/associations', self.association, user='moderator'
        )
        check_snapshot('associations_remove', removed)

    @contract(('GET', '/associations-history'))
    def test_history(self):
        self.post('/associations', self.association, user='contributor')
        response = self.get('/associations-history', params={'d': self.child})
        check_snapshot('associations_history', response)
        assert response.json['count'] >= 1

    @contract(('GET', '/documents/changes'))
    def test_changes(self):
        response = self.get('/documents/changes', params={'limit': 5})
        check_snapshot('documents_changes', response)
