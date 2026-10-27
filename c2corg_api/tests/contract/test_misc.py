import json
from unittest.mock import Mock, patch

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


class TestCoverageLookup(DocumentContractTest):
    @contract(('GET', '/getcoverage'))
    def test_coverage_of_a_point(self):
        response = self.get('/getcoverage', params={'lon': 5.71, 'lat': 45.655})
        check_snapshot('getcoverage', response)

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
