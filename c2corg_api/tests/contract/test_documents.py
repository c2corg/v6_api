from unittest.mock import Mock, patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests.contract import ContractTest, check_snapshot, contract
from c2corg_api.tests.search.__init__ import reset_search_index

POINT = '{"type": "Point", "coordinates": [635956, 5723604]}'
LINE = '{"type": "LineString", "coordinates": [[635956, 5723604], [635966, 5723644]]}'
POLYGON = (
    '{"type": "Polygon", "coordinates": [[[635000, 5723000], [635000, 5724000], '
    '[637000, 5724000], [637000, 5723000], [635000, 5723000]]]}'
)

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

    def setUp(self):
        self.ids = {'profiles': self.global_userids['contributor']}
        self.ids['waypoints'] = self.create(
            'waypoints',
            {
                'waypoint_type': 'summit',
                'elevation': 3779,
                'geometry': {'geom': POINT},
                'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
            },
        )
        waypoint = [{'document_id': self.ids['waypoints']}]
        self.ids['routes'] = self.create(
            'routes',
            {
                'main_waypoint_id': self.ids['waypoints'],
                'activities': ['hiking'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'geometry': {'geom_detail': LINE},
                'locales': [{'lang': 'en', 'title': 'Some nice loop', 'gear': 'shoes'}],
                'associations': {'waypoints': waypoint},
            },
        )
        self.ids['outings'] = self.create(
            'outings',
            {
                'activities': ['hiking'],
                'date_start': '2016-01-01',
                'date_end': '2016-01-02',
                'elevation_max': 1500,
                'geometry': {'geom_detail': LINE},
                'locales': [{'lang': 'en', 'title': 'A nice day', 'weather': 'sunny'}],
                'associations': {
                    'users': [{'document_id': self.global_userids['contributor']}],
                    'routes': [{'document_id': self.ids['routes']}],
                },
            },
        )
        self.ids['articles'] = self.create(
            'articles',
            {
                'categories': ['site_info'],
                'activities': ['hiking'],
                'article_type': 'collab',
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
                'associations': {'waypoints': waypoint},
            },
        )
        self.ids['books'] = self.create(
            'books',
            {
                'activities': ['hiking'],
                'book_types': ['biography'],
                'author': 'Author',
                'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
                'associations': {'waypoints': waypoint},
            },
        )
        with patch(
            'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
        ):
            self.ids['images'] = self.create(
                'images',
                {
                    'filename': 'image.jpg',
                    'activities': ['hiking'],
                    'image_type': 'collaborative',
                    'height': 1500,
                    'geometry': {'geom': POINT},
                    'locales': [{'lang': 'en', 'title': 'A view'}],
                    'associations': {'waypoints': waypoint},
                },
            )
        self.ids['xreports'] = self.create(
            'xreports',
            {
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 5,
                'geometry': {'geom': POINT},
                'locales': [{'lang': 'en', 'title': 'Stone fall'}],
            },
        )
        self.ids['areas'] = self.create(
            'areas',
            {
                'area_type': 'range',
                'geometry': {'geom_detail': POLYGON},
                'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
            },
            user='moderator',
        )
        self.ids['maps'] = self.create(
            'maps',
            {
                'editor': 'IGN',
                'scale': '25000',
                'code': '3432OT',
                'geometry': {'geom_detail': POLYGON},
                'locales': [{'lang': 'en', 'title': 'Annecy'}],
            },
            user='moderator',
        )
        self.ids['coverages'] = self.create(
            'coverages',
            {
                'coverage_type': 'fr-se',
                'geometry': {'geom_detail': POLYGON},
                'locales': [{'lang': 'en', 'title': 'Coverage'}],
            },
        )

    def create(self, prefix, body, user='contributor'):
        """Create a document through the API and return its id."""
        return self.post(f'/{prefix}', body, user=user).json['document_id']

    def url(self, prefix, path=''):
        return f'/{prefix}/{self.ids[prefix]}{path}'


class TestDocumentGet(DocumentContractTest):
    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get(self, prefix):
        check_snapshot(f'{prefix}_get', self.get(self.url(prefix)))

    @contract(*_routes('GET', '/{prefix}/{{id}}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_get_lang(self, prefix):
        check_snapshot(
            f'{prefix}_get_lang', self.get(self.url(prefix), params={'l': 'en'})
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['routes', 'waypoints']))
    @pytest.mark.parametrize('prefix', ['routes', 'waypoints'])
    def test_get_cooked(self, prefix):
        check_snapshot(
            f'{prefix}_get_cooked', self.get(self.url(prefix), params={'cook': 'en'})
        )

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_for_editing(self):
        # the editing view: no ETag (not cached), no custom associations
        response = self.get(self.url('waypoints'), params={'e': '1', 'l': 'en'})
        check_snapshot('waypoints_get_editing', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    @pytest.mark.parametrize(
        'params', [{'cook': 'en', 'e': '1'}, {'cook': 'en', 'l': 'en'}]
    )
    def test_get_cooked_with_other_params(self, params):
        response = self.get(self.url('waypoints'), params=params, status=400)
        check_snapshot('waypoints_get_cooked_invalid', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['waypoints']))
    def test_get_not_modified(self):
        etag = self.get(self.url('waypoints')).headers['ETag']
        response = self.get(
            self.url('waypoints'), headers={'If-None-Match': etag}, status=304
        )
        check_snapshot('waypoints_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_not_modified_book(self):
        etag = self.get(self.url('books')).headers['ETag']
        response = self.get(
            self.url('books'), headers={'If-None-Match': etag}, status=304
        )
        check_snapshot('books_get_not_modified', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    def test_get_unknown_book(self):
        check_snapshot('books_get_not_found', self.get('/books/9999999', status=404))

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['books']))
    @pytest.mark.parametrize('book_id', ['abc', '-1'])
    def test_get_invalid_id(self, book_id):
        response = self.get(f'/books/{book_id}', status=400)
        check_snapshot('books_get_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', ['books']))
    def test_get_invalid_version_id(self):
        response = self.get(self.url('books', '/en/abc'), status=400)
        check_snapshot('books_version_invalid_id', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['xreports']))
    @pytest.mark.parametrize('user', ['contributor', 'moderator', 'contributor2'])
    def test_get_xreport_as(self, user):
        # the personal fields are for its author and the moderators only
        response = self.get(self.url('xreports'), user=user)
        check_snapshot(f'xreports_get_as_{user}', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_private_profile_as_user(self):
        # a private profile is shown to the authenticated users only
        response = self.get(self.url('profiles'), user='contributor2')
        check_snapshot('profiles_get_as_user', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_public_profile(self):
        user = self.session.get(User, self.global_userids['contributor'])
        user.is_profile_public = True
        self.session.flush()
        check_snapshot('profiles_get_public', self.get(self.url('profiles')))

    @contract(*_routes('GET', '/{prefix}/{{id}}', ['profiles']))
    def test_get_unknown_profile(self):
        response = self.get('/profiles/9999999', status=404)
        check_snapshot('profiles_get_unknown', response)

    @contract(*_routes('GET', '/{prefix}/{{id}}/{{lang}}/info', WITH_INFO))
    @pytest.mark.parametrize('prefix', WITH_INFO)
    def test_info(self, prefix):
        check_snapshot(f'{prefix}_info', self.get(self.url(prefix, '/en/info')))

    @contract(
        *_routes('GET', '/{prefix}/{{id}}/{{lang}}/{{version_id}}', WITH_VERSION),
        ('GET', '/document/{id}/history/{lang}'),
    )
    @pytest.mark.parametrize('prefix', WITH_VERSION)
    def test_version(self, prefix):
        history = self.get(f'/document/{self.ids[prefix]}/history/en')
        check_snapshot(f'{prefix}_history', history)
        version_id = history.json['versions'][0]['version_id']
        response = self.get(self.url(prefix, f'/en/{version_id}'))
        check_snapshot(f'{prefix}_version', response)


class TestDocumentListing(DocumentContractTest):
    @contract(*_routes('GET', '/{prefix}', DOCUMENT_TYPES))
    @pytest.mark.parametrize('prefix', DOCUMENT_TYPES)
    def test_listing(self, prefix):
        # /profiles is the only listing that needs a user
        user = 'contributor' if prefix == 'profiles' else None
        response = self.get(f'/{prefix}', user=user, params={'limit': 2})
        check_snapshot(f'{prefix}_listing', response)
        assert len(response.json['documents']) <= 2
        assert response.json['total'] >= len(response.json['documents'])

    @contract(*_routes('GET', '/{prefix}', ['waypoints']))
    def test_listing_lang_and_pagination(self):
        response = self.get('/waypoints', params={'pl': 'fr', 'offset': 1, 'limit': 1})
        check_snapshot('waypoints_listing_pl', response)

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_with_filters(self):
        # filters make the listing search with ElasticSearch; rebuilding the
        # index is slow, so one test for the filtered listings
        reset_search_index(self.session)
        response = self.get(
            '/outings', params={'act': 'hiking,skitouring', 'pl': 'en', 'limit': 5}
        )
        check_snapshot('outings_listing_filtered', response)
        ids = [d['document_id'] for d in response.json['documents']]
        assert self.ids['outings'] in ids

    @contract(*_routes('GET', '/{prefix}', ['outings']))
    def test_listing_beyond_the_search_window(self):
        response = self.get(
            '/outings', params={'offset': 9990, 'limit': 20}, status=400
        )
        check_snapshot('outings_listing_beyond_window', response)

    @contract(('GET', '/profiles'))
    def test_profiles_listing_needs_a_user(self):
        check_snapshot('profiles_listing_anonymous', self.get('/profiles', status=403))


class TestPathsLikeADocument(ContractTest):
    """Paths that look like a document page, with another route."""

    @contract(('POST', '/images/list'))
    def test_get_image_list(self):
        # a POST-only route: GET is not allowed (it is not image "list")
        response = self.get('/images/list', status=405)
        check_snapshot('images_list_get', response)

    @contract(('GET', '/routes/update_public_transportation_rating'))
    def test_update_public_transportation_rating_needs_a_moderator(self):
        response = self.get(
            '/routes/update_public_transportation_rating',
            user='contributor',
            status=403,
        )
        check_snapshot('routes_update_public_transportation_rating_forbidden', response)
