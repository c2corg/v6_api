from unittest.mock import Mock, patch

import pytest

from c2corg_api.tests.contract import ContractTest, check_snapshot, contract

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

    @contract(('GET', '/profiles'))
    def test_profiles_listing_needs_a_user(self):
        check_snapshot('profiles_listing_anonymous', self.get('/profiles', status=403))
