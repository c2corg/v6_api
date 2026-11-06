from unittest.mock import patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests.contract import Browser, ContractTest, check_snapshot, contract
from c2corg_api.tests.contract.documents import (  # noqa: F401 (re-exported)
    LINE,
    POINT,
    POLYGON,
    create_documents,
)
from c2corg_api.tests.search.__init__ import reset_search_index

# the document types, by URL prefix
DOCUMENT_TYPES = [
    'areas',
    'articles',
    'books',
    'coverages',
    'images',
    'maps',
    'outings',
    'profiles',
    'routes',
    'waypoints',
    'xreports',
]
# the types with an /{id}/{lang}/info route
WITH_INFO = [t for t in DOCUMENT_TYPES if t != 'coverages']
# the types with an /{id}/{lang}/{version_id} route
WITH_VERSION = [t for t in DOCUMENT_TYPES if t not in ('coverages', 'maps', 'profiles')]


def _routes(method, path, types):
    return [(method, path.format(prefix=prefix)) for prefix in types]


class DocumentContractTest(ContractTest):
    """One document of each type, created through the API."""

    @pytest.fixture(autouse=True)
    def _setup_document_contract_test(self, client, settings, user_ids):
        self.documents = create_documents(Browser(client, settings), user_ids)
        self.ids = self.documents.ids

    def create(self, client, settings, prefix, body, user='contributor'):
        return Browser(client, settings).create(prefix, body, user=user)

    def url(self, user_ids, prefix, path=''):
        return f'/{prefix}/{self.ids[prefix]}{path}'


class TestDocumentGet(DocumentContractTest):
    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get(self, prefix, client, settings, user_ids):
        check_snapshot(
            f'{prefix}_get', self.get(client, settings, self.url(user_ids, prefix))
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get_lang(self, prefix, client, settings, user_ids):
        check_snapshot(
            f'{prefix}_get_lang',
            self.get(client, settings, self.url(user_ids, prefix), params={'l': 'en'}),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['routes', 'waypoints']))
    @pytest.mark.parametrize('prefix', ['routes', 'waypoints'])
    def test_get_cooked(self, prefix, client, settings, user_ids):
        check_snapshot(
            f'{prefix}_get_cooked',
            self.get(
                client, settings, self.url(user_ids, prefix), params={'cook': 'en'}
            ),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_for_editing(self, client, settings, user_ids):
        # the editing view: no ETag (not cached), no custom associations
        response = self.get(
            client,
            settings,
            self.url(user_ids, 'waypoints'),
            params={'e': '1', 'l': 'en'},
        )
        check_snapshot('waypoints_get_editing', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    @pytest.mark.parametrize(
        'params', [{'cook': 'en', 'e': '1'}, {'cook': 'en', 'l': 'en'}]
    )
    def test_get_cooked_with_other_params(self, params, client, settings, user_ids):
        response = self.get(
            client, settings, self.url(user_ids, 'waypoints'), params=params, status=400
        )
        check_snapshot('waypoints_get_cooked_invalid', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_not_modified(self, client, settings, user_ids):
        etag = self.get(client, settings, self.url(user_ids, 'waypoints')).headers[
            'ETag'
        ]
        response = self.get(
            client,
            settings,
            self.url(user_ids, 'waypoints'),
            headers={'If-None-Match': etag},
            status=304,
        )
        check_snapshot('waypoints_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_not_modified_book(self, client, settings, user_ids):
        etag = self.get(client, settings, self.url(user_ids, 'books')).headers['ETag']
        response = self.get(
            client,
            settings,
            self.url(user_ids, 'books'),
            headers={'If-None-Match': etag},
            status=304,
        )
        check_snapshot('books_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_unknown_book(self, client, settings):
        check_snapshot(
            'books_get_not_found',
            self.get(client, settings, '/books/9999999', status=404),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    @pytest.mark.parametrize('book_id', ['abc', '-1'])
    def test_get_invalid_id(self, book_id, client, settings):
        response = self.get(client, settings, f'/books/{book_id}', status=404)
        check_snapshot('books_get_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', ['books']))
    def test_get_invalid_version_id(self, client, settings, user_ids):
        response = self.get(
            client, settings, self.url(user_ids, 'books', '/en/abc'), status=404
        )
        check_snapshot('books_version_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['xreports']))
    @pytest.mark.parametrize('user', ['contributor', 'moderator', 'contributor2'])
    def test_get_xreport_as(self, user, client, settings, user_ids):
        # the personal fields are for its author and the moderators only
        response = self.get(client, settings, self.url(user_ids, 'xreports'), user=user)
        check_snapshot(f'xreports_get_as_{user}', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_private_profile_as_user(self, client, settings, user_ids):
        # a private profile is shown to the authenticated users only
        response = self.get(
            client, settings, self.url(user_ids, 'profiles'), user='contributor2'
        )
        check_snapshot('profiles_get_as_user', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_public_profile(self, client, session, settings, user_ids):
        user = session.get(User, user_ids['contributor'])
        user.is_profile_public = True
        session.flush()
        check_snapshot(
            'profiles_get_public',
            self.get(client, settings, self.url(user_ids, 'profiles')),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_unknown_profile(self, client, settings):
        response = self.get(client, settings, '/profiles/9999999', status=404)
        check_snapshot('profiles_get_unknown', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/info', WITH_INFO))
    @pytest.mark.parametrize('prefix', WITH_INFO)
    def test_info(self, prefix, client, settings, user_ids):
        check_snapshot(
            f'{prefix}_info',
            self.get(client, settings, self.url(user_ids, prefix, '/en/info')),
        )

    @contract(
        *_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', WITH_VERSION),
        ('GET', '/document/{id}/history/{lang}'),
    )
    @pytest.mark.parametrize('prefix', WITH_VERSION)
    def test_version(self, prefix, client, settings, user_ids):
        history = self.get(client, settings, f'/document/{self.ids[prefix]}/history/en')
        check_snapshot(f'{prefix}_history', history)
        version_id = history.json['versions'][0]['version_id']
        response = self.get(
            client, settings, self.url(user_ids, prefix, f'/en/{version_id}')
        )
        check_snapshot(f'{prefix}_version', response)


class TestDocumentListing(DocumentContractTest):
    @contract(*_routes('GET', '/{prefix}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_listing(self, prefix, client, settings):
        # /profiles is the only listing that needs a user
        user = 'contributor' if prefix == 'profiles' else None
        response = self.get(
            client, settings, f'/{prefix}', user=user, params={'limit': 2}
        )
        check_snapshot(f'{prefix}_listing', response)
        assert len(response.json['documents']) <= 2
        assert response.json['total'] >= len(response.json['documents'])

    @contract(*_routes('GET', '/{prefix}', ['waypoints']))
    def test_listing_lang_and_pagination(self, client, settings):
        response = self.get(
            client, settings, '/waypoints', params={'pl': 'fr', 'offset': 1, 'limit': 1}
        )
        check_snapshot('waypoints_listing_pl', response)

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_with_filters(self, client, session, settings):
        # filters make the listing search with ElasticSearch; rebuilding the
        # index is slow, so one test for the filtered listings
        reset_search_index(session)
        response = self.get(
            client,
            settings,
            '/outings',
            params={'act': 'hiking,skitouring', 'pl': 'en', 'limit': 5},
        )
        check_snapshot('outings_listing_filtered', response)
        ids = [d['document_id'] for d in response.json['documents']]
        assert self.ids['outings'] in ids

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_beyond_the_search_window(self, client, settings):
        response = self.get(
            client,
            settings,
            '/outings',
            params={'offset': 9990, 'limit': 20},
            status=400,
        )
        check_snapshot('outings_listing_beyond_window', response)

    @contract(('GET', '/profiles'))
    def test_profiles_listing_needs_a_user(self, client, settings):
        check_snapshot(
            'profiles_listing_anonymous',
            self.get(client, settings, '/profiles', status=403),
        )


@pytest.mark.usefixtures('client')
class TestPathsLikeADocument(ContractTest):
    """Paths that look like a document page, with another route."""

    @contract(('POST', '/images/list'))
    def test_get_image_list(self, client, settings):
        # a POST-only route: GET is not allowed (it is not image "list")
        response = self.get(client, settings, '/images/list', status=405)
        check_snapshot('images_list_get', response)

    @contract(('POST', '/routes/update_public_transportation_rating'))
    def test_update_public_transportation_rating_needs_a_moderator(
        self, client, settings
    ):
        response = self.post(
            client,
            settings,
            '/routes/update_public_transportation_rating',
            None,
            user='contributor',
            status=403,
        )
        check_snapshot('routes_update_public_transportation_rating_forbidden', response)

    @contract(('POST', '/routes/update_public_transportation_rating'))
    def test_update_public_transportation_rating(self, client, settings):
        # the ratings of the routes are updated
        with patch(
            'c2corg_api.views.route.update_all_pt_rating'
        ) as update_all_pt_rating:
            response = self.post(
                client,
                settings,
                '/routes/update_public_transportation_rating',
                None,
                user='moderator',
            )
        check_snapshot('routes_update_public_transportation_rating', response)
        update_all_pt_rating.assert_called_once_with(True)
