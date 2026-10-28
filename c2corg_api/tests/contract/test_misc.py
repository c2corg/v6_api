import json
from unittest.mock import Mock, patch

from c2corg_api.models.user import User
from c2corg_api.tests.contract import ContractTest, check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT, DocumentContractTest
from c2corg_api.tests.search.__init__ import reset_search_index

# the coverage polygon of DocumentContractTest, in EPSG:4326
POLYGON_4326 = json.dumps(
    {
        'type': 'Polygon',
        'coordinates': [
            [[5.70, 45.65], [5.70, 45.66], [5.72, 45.66], [5.72, 45.65], [5.70, 45.65]]
        ],
    }
)


class TestMisc(DocumentContractTest):
    @contract(('GET', '/health'))
    def test_health(self):
        check_snapshot('health', self.get('/health'))

    @contract(('POST', '/cooker'))
    def test_cooker(self):
        body = {'lang': 'en', 'description': '**bold** [[waypoints/1|a link]]'}
        check_snapshot('cooker', self.post('/cooker', body))

    @contract(('GET', '/search'))
    def test_search(self):
        # rebuilding the index is slow: one test for all the search cases
        reset_search_index(self.session)
        response = self.get('/search', params={'q': 'Mont Pourri', 'pl': 'en'})
        check_snapshot('search', response)
        waypoints = response.json['waypoints']['documents']
        assert self.ids['waypoints'] in [d['document_id'] for d in waypoints]
        # one type only, paginated
        response = self.get('/search', params={'q': 'Mont', 't': 'w', 'limit': 1})
        check_snapshot('search_one_type', response)


class TestSearchErrors(ContractTest):
    @contract(('GET', '/search'))
    def test_invalid_parameters(self):
        response = self.get(
            '/search', params={'q': 'x', 'limit': 'many', 'pl': 'xx'}, status=400
        )
        check_snapshot('search_invalid_parameters', response)
        assert response.json['errors'] == [
            {
                'location': 'querystring',
                'name': 'limit',
                'description': 'invalid limit',
            },
            {'location': 'querystring', 'name': 'lang', 'description': 'invalid lang'},
        ]


class TestFeeds(DocumentContractTest):
    @contract(('GET', '/feed'))
    def test_feed(self):
        check_snapshot('feed', self.get('/feed', params={'limit': 3}))

    @contract(('GET', '/personal-feed'))
    def test_personal_feed(self):
        response = self.get('/personal-feed', user='contributor', params={'limit': 3})
        check_snapshot('personal_feed', response)

    @contract(('GET', '/profile-feed'))
    def test_profile_feed(self):
        # profiles are private unless their owner makes them public
        params = {'u': self.global_userids['contributor'], 'limit': 3}
        response = self.get('/profile-feed', user='contributor', params=params)
        check_snapshot('profile_feed', response)

    @contract(('GET', '/feed'))
    def test_feed_next_page(self):
        token = self.get('/feed', params={'limit': 1}).json['pagination_token']
        response = self.get('/feed', params={'limit': 1, 'token': token, 'pl': 'en'})
        check_snapshot('feed_next_page', response)

    @contract(('GET', '/feed'))
    def test_feed_invalid_parameters(self):
        # an invalid pagination token, not a password
        params = {'token': 'abc', 'limit': 'x'}  # nosec B105
        response = self.get('/feed', params=params, status=400)
        check_snapshot('feed_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['limit', 'token']

    @contract(('GET', '/personal-feed'))
    def test_personal_feed_needs_a_user(self):
        response = self.get('/personal-feed', status=403)
        check_snapshot('personal_feed_anonymous', response)

    @contract(('GET', '/profile-feed'))
    def test_private_profile_feed_needs_a_user(self):
        params = {'u': self.global_userids['contributor']}
        response = self.get('/profile-feed', params=params, status=403)
        check_snapshot('profile_feed_private', response)
        assert response.json['errors'][0]['description'] == (
            'no permission to see the feed'
        )

    @contract(('GET', '/profile-feed'))
    def test_public_profile_feed(self):
        user = self.session.get(User, self.global_userids['contributor'])
        user.is_profile_public = True
        self.session.flush()
        params = {'u': user.id, 'limit': 3}
        check_snapshot('profile_feed_public', self.get('/profile-feed', params=params))

    @contract(('GET', '/profile-feed'))
    def test_profile_feed_of_unknown_user(self):
        response = self.get('/profile-feed', params={'u': 9999999}, status=404)
        check_snapshot('profile_feed_unknown_user', response)

    @contract(('GET', '/profile-feed'))
    def test_profile_feed_without_user(self):
        response = self.get('/profile-feed', status=400)
        check_snapshot('profile_feed_without_user', response)
        assert [e['name'] for e in response.json['errors']] == ['u']


class TestSitemaps(DocumentContractTest):
    @contract(('GET', '/sitemaps'), ('GET', '/sitemaps/{doc_type}/{i}'))
    def test_sitemaps(self):
        check_snapshot('sitemaps', self.get('/sitemaps'))
        check_snapshot('sitemaps_waypoints', self.get('/sitemaps/w/0'))

    @contract(('GET', '/sitemaps.xml'), ('GET', '/sitemaps.xml/{doc_type}/{i}.xml'))
    def test_sitemaps_xml(self):
        index = self.get('/sitemaps.xml')
        check_snapshot('sitemaps_xml', index)
        assert b'<sitemapindex' in index.body
        waypoints = self.get('/sitemaps.xml/w/0.xml')
        check_snapshot('sitemaps_xml_waypoints', waypoints)
        assert b'<urlset' in waypoints.body

    @contract(('GET', '/sitemaps'), ('GET', '/sitemaps.xml'))
    def test_not_modified(self):
        for url, name in [('/sitemaps', 'sitemaps'), ('/sitemaps.xml', 'sitemaps_xml')]:
            etag = self.get(url).headers['ETag']
            response = self.get(url, headers={'If-None-Match': etag}, status=304)
            check_snapshot(f'{name}_not_modified', response)

    @contract(('GET', '/sitemaps/{doc_type}/{i}'))
    def test_invalid_page(self):
        response = self.get('/sitemaps/z/x', status=400)
        check_snapshot('sitemaps_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['i', 'doc_type']

    @contract(('GET', '/sitemaps.xml/{doc_type}/{i}.xml'))
    def test_invalid_page_xml(self):
        response = self.get('/sitemaps.xml/z/x.xml', status=400)
        check_snapshot('sitemaps_xml_invalid', response)
        assert [e['name'] for e in response.json['errors']] == ['i', 'doc_type']

    @contract(
        ('GET', '/sitemaps/{doc_type}/{i}'), ('GET', '/sitemaps.xml/{doc_type}/{i}.xml')
    )
    def test_page_without_documents(self):
        check_snapshot('sitemaps_empty_page', self.get('/sitemaps/w/99', status=404))
        response = self.get('/sitemaps.xml/w/99.xml', status=404)
        check_snapshot('sitemaps_xml_empty_page', response)


class TestCoverageLookup(DocumentContractTest):
    @contract(('GET', '/getcoverage'))
    def test_coverage_of_a_point(self):
        response = self.get('/getcoverage', params={'lon': 5.71, 'lat': 45.655})
        check_snapshot('getcoverage', response)

    @contract(('GET', '/getcoverage'))
    def test_no_coverage(self):
        response = self.get('/getcoverage', params={'lon': 0, 'lat': 0})
        check_snapshot('getcoverage_none', response)
        assert response.json is None

    @contract(('POST', '/getpolygoncoverage'))
    def test_coverages_of_a_polygon(self):
        response = self.post('/getpolygoncoverage', {'geom_detail': POLYGON_4326})
        check_snapshot('getpolygoncoverage', response)


class TestImageRoutes(DocumentContractTest):
    @contract(('POST', '/images/list'))
    def test_create_a_list(self):
        image = {
            'filename': 'list.jpg',
            'activities': ['hiking'],
            'image_type': 'collaborative',
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'From a list'}],
            'associations': {'waypoints': [{'document_id': self.ids['waypoints']}]},
        }
        with patch(
            'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
        ):
            response = self.post(
                '/images/list', {'images': [image]}, user='contributor'
            )
        check_snapshot('images_list', response)

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy(self):
        response = self.get(
            f'/images/proxy/{self.ids["images"]}', params={'size': 'MI'}, status=302
        )
        check_snapshot('images_proxy', response)

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy_original(self):
        response = self.get(f'/images/proxy/{self.ids["images"]}', status=302)
        check_snapshot('images_proxy_original', response)
        assert response.body.startswith(b'302 Found\n\nThe resource was found at ')

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy_errors(self):
        check_snapshot(
            'images_proxy_unknown', self.get('/images/proxy/9999999', status=404)
        )
        response = self.get(
            f'/images/proxy/{self.ids["images"]}', params={'size': 'XX'}, status=400
        )
        check_snapshot('images_proxy_invalid_size', response)
        assert [e['name'] for e in response.json['errors']] == ['size']
