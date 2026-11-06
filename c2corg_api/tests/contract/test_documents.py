from unittest.mock import patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests.contract import check_snapshot, contract
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


@pytest.mark.usefixtures('documents')
class TestDocumentGet:
    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get(self, prefix, browser, documents):
        check_snapshot(f'{prefix}_get', browser.get(documents.url(prefix)))

    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get_lang(self, prefix, browser, documents):
        check_snapshot(
            f'{prefix}_get_lang',
            browser.get(documents.url(prefix), params={'l': 'en'}),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['routes', 'waypoints']))
    @pytest.mark.parametrize('prefix', ['routes', 'waypoints'])
    def test_get_cooked(self, prefix, browser, documents):
        check_snapshot(
            f'{prefix}_get_cooked',
            browser.get(documents.url(prefix), params={'cook': 'en'}),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_for_editing(self, browser, documents):
        # the editing view: no ETag (not cached), no custom associations
        response = browser.get(
            documents.url('waypoints'),
            params={'e': '1', 'l': 'en'},
        )
        check_snapshot('waypoints_get_editing', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    @pytest.mark.parametrize(
        'params', [{'cook': 'en', 'e': '1'}, {'cook': 'en', 'l': 'en'}]
    )
    def test_get_cooked_with_other_params(self, params, browser, documents):
        response = browser.get(documents.url('waypoints'), params=params, status=400)
        check_snapshot('waypoints_get_cooked_invalid', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_not_modified(self, browser, documents):
        etag = browser.get(documents.url('waypoints')).headers['ETag']
        response = browser.get(
            documents.url('waypoints'),
            headers={'If-None-Match': etag},
            status=304,
        )
        check_snapshot('waypoints_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_not_modified_book(self, browser, documents):
        etag = browser.get(documents.url('books')).headers['ETag']
        response = browser.get(
            documents.url('books'),
            headers={'If-None-Match': etag},
            status=304,
        )
        check_snapshot('books_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_unknown_book(self, browser):
        check_snapshot(
            'books_get_not_found',
            browser.get('/books/9999999', status=404),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    @pytest.mark.parametrize('book_id', ['abc', '-1'])
    def test_get_invalid_id(self, book_id, browser):
        response = browser.get(f'/books/{book_id}', status=404)
        check_snapshot('books_get_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', ['books']))
    def test_get_invalid_version_id(self, browser, documents):
        response = browser.get(documents.url('books', '/en/abc'), status=404)
        check_snapshot('books_version_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['xreports']))
    @pytest.mark.parametrize('user', ['contributor', 'moderator', 'contributor2'])
    def test_get_xreport_as(self, user, browser, documents):
        # the personal fields are for its author and the moderators only
        response = browser.get(documents.url('xreports'), user=user)
        check_snapshot(f'xreports_get_as_{user}', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_private_profile_as_user(self, browser, documents):
        # a private profile is shown to the authenticated users only
        response = browser.get(documents.url('profiles'), user='contributor2')
        check_snapshot('profiles_get_as_user', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_public_profile(self, session, user_ids, browser, documents):
        user = session.get(User, user_ids['contributor'])
        user.is_profile_public = True
        session.flush()
        check_snapshot(
            'profiles_get_public',
            browser.get(documents.url('profiles')),
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_unknown_profile(self, browser):
        response = browser.get('/profiles/9999999', status=404)
        check_snapshot('profiles_get_unknown', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/info', WITH_INFO))
    @pytest.mark.parametrize('prefix', WITH_INFO)
    def test_info(self, prefix, browser, documents):
        check_snapshot(
            f'{prefix}_info',
            browser.get(documents.url(prefix, '/en/info')),
        )

    @contract(
        *_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', WITH_VERSION),
        ('GET', '/document/{id}/history/{lang}'),
    )
    @pytest.mark.parametrize('prefix', WITH_VERSION)
    def test_version(self, prefix, browser, documents):
        history = browser.get(f'/document/{documents.ids[prefix]}/history/en')
        check_snapshot(f'{prefix}_history', history)
        version_id = history.json['versions'][0]['version_id']
        response = browser.get(documents.url(prefix, f'/en/{version_id}'))
        check_snapshot(f'{prefix}_version', response)


@pytest.mark.usefixtures('documents')
class TestDocumentListing:
    @contract(*_routes('GET', '/{prefix}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_listing(self, prefix, browser):
        # /profiles is the only listing that needs a user
        user = 'contributor' if prefix == 'profiles' else None
        response = browser.get(f'/{prefix}', user=user, params={'limit': 2})
        check_snapshot(f'{prefix}_listing', response)
        assert len(response.json['documents']) <= 2
        assert response.json['total'] >= len(response.json['documents'])

    @contract(*_routes('GET', '/{prefix}', ['waypoints']))
    def test_listing_lang_and_pagination(self, browser):
        response = browser.get(
            '/waypoints', params={'pl': 'fr', 'offset': 1, 'limit': 1}
        )
        check_snapshot('waypoints_listing_pl', response)

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_with_filters(self, session, browser, documents):
        # filters make the listing search with ElasticSearch; rebuilding the
        # index is slow, so one test for the filtered listings
        reset_search_index(session)
        response = browser.get(
            '/outings',
            params={'act': 'hiking,skitouring', 'pl': 'en', 'limit': 5},
        )
        check_snapshot('outings_listing_filtered', response)
        ids = [d['document_id'] for d in response.json['documents']]
        assert documents.ids['outings'] in ids

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_beyond_the_search_window(self, browser):
        response = browser.get(
            '/outings',
            params={'offset': 9990, 'limit': 20},
            status=400,
        )
        check_snapshot('outings_listing_beyond_window', response)

    @contract(('GET', '/profiles'))
    def test_profiles_listing_needs_a_user(self, browser):
        check_snapshot(
            'profiles_listing_anonymous',
            browser.get('/profiles', status=403),
        )


@pytest.mark.usefixtures('client')
class TestPathsLikeADocument:
    """Paths that look like a document page, with another route."""

    @contract(('POST', '/images/list'))
    def test_get_image_list(self, browser):
        # a POST-only route: GET is not allowed (it is not image "list")
        response = browser.get('/images/list', status=405)
        check_snapshot('images_list_get', response)

    @contract(('POST', '/routes/update_public_transportation_rating'))
    def test_update_public_transportation_rating_needs_a_moderator(self, browser):
        response = browser.post(
            '/routes/update_public_transportation_rating',
            None,
            user='contributor',
            status=403,
        )
        check_snapshot('routes_update_public_transportation_rating_forbidden', response)

    @contract(('POST', '/routes/update_public_transportation_rating'))
    def test_update_public_transportation_rating(self, browser):
        # the ratings of the routes are updated
        with patch(
            'c2corg_api.views.route.update_all_pt_rating'
        ) as update_all_pt_rating:
            response = browser.post(
                '/routes/update_public_transportation_rating',
                None,
                user='moderator',
            )
        check_snapshot('routes_update_public_transportation_rating', response)
        update_all_pt_rating.assert_called_once_with(True)
