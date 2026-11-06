import json
from unittest.mock import Mock, patch

import pytest

from c2corg_api.models.user import User
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT
from c2corg_api.tests.search.__init__ import reset_search_index

# the coverage polygon of the documents fixture, in EPSG:4326
POLYGON_4326 = json.dumps(
    {
        'type': 'Polygon',
        'coordinates': [
            [[5.70, 45.65], [5.70, 45.66], [5.72, 45.66], [5.72, 45.65], [5.70, 45.65]]
        ],
    }
)


@pytest.mark.usefixtures('documents')
class TestMisc:
    @contract(('GET', '/health'))
    def test_health(self, browser):
        check_snapshot('health', browser.get('/health'))

    @contract(('POST', '/cooker'))
    def test_cooker(self, browser):
        body = {'lang': 'en', 'description': '**bold** [[waypoints/1|a link]]'}
        check_snapshot('cooker', browser.post('/cooker', body))

    @contract(('GET', '/search'))
    def test_search(self, session, browser, documents):
        # rebuilding the index is slow: one test for all the search cases
        reset_search_index(session)
        response = browser.get('/search', params={'q': 'Mont Pourri', 'pl': 'en'})
        check_snapshot('search', response)
        waypoints = response.json['waypoints']['documents']
        assert documents.ids['waypoints'] in [d['document_id'] for d in waypoints]
        # one type only, paginated
        response = browser.get('/search', params={'q': 'Mont', 't': 'w', 'limit': 1})
        check_snapshot('search_one_type', response)


@pytest.mark.usefixtures('client')
class TestSearchErrors:
    @contract(('GET', '/search'))
    def test_invalid_parameters(self, browser):
        response = browser.get(
            '/search',
            params={'q': 'x', 'limit': 'many', 'pl': 'xx'},
            status=422,
        )
        check_snapshot('search_invalid_parameters', response)
        assert invalid_parameters(response) == [
            ('query', 'limit', 'invalid limit'),
            ('query', 'pl', 'invalid lang'),
        ]


@pytest.mark.usefixtures('documents')
class TestFeeds:
    @contract(('GET', '/feed'))
    def test_feed(self, browser):
        check_snapshot('feed', browser.get('/feed', params={'limit': 3}))

    @contract(('GET', '/personal-feed'))
    def test_personal_feed(self, browser):
        response = browser.get(
            '/personal-feed', user='contributor', params={'limit': 3}
        )
        check_snapshot('personal_feed', response)

    @contract(('GET', '/profile-feed'))
    def test_profile_feed(self, user_ids, browser):
        # profiles are private unless their owner makes them public
        params = {'u': user_ids['contributor'], 'limit': 3}
        response = browser.get('/profile-feed', user='contributor', params=params)
        check_snapshot('profile_feed', response)

    @contract(('GET', '/feed'))
    def test_feed_next_page(self, browser):
        token = browser.get('/feed', params={'limit': 1}).json['pagination_token']
        response = browser.get('/feed', params={'limit': 1, 'token': token, 'pl': 'en'})
        check_snapshot('feed_next_page', response)

    @contract(('GET', '/feed'))
    def test_feed_invalid_parameters(self, browser):
        # an invalid pagination token, not a password
        params = {'token': 'abc', 'limit': 'x'}  # nosec B105
        response = browser.get('/feed', params=params, status=422)
        check_snapshot('feed_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == [
            'limit',
            'token',
        ]

    @contract(('GET', '/personal-feed'))
    def test_personal_feed_needs_a_user(self, browser):
        response = browser.get('/personal-feed', status=403)
        check_snapshot('personal_feed_anonymous', response)

    @contract(('GET', '/profile-feed'))
    def test_private_profile_feed_needs_a_user(self, user_ids, browser):
        params = {'u': user_ids['contributor']}
        response = browser.get('/profile-feed', params=params, status=403)
        check_snapshot('profile_feed_private', response)
        assert response.json['errors'][0]['description'] == (
            'no permission to see the feed'
        )

    @contract(('GET', '/profile-feed'))
    def test_public_profile_feed(self, session, user_ids, browser):
        user = session.get(User, user_ids['contributor'])
        user.is_profile_public = True
        session.flush()
        params = {'u': user.id, 'limit': 3}
        check_snapshot(
            'profile_feed_public',
            browser.get('/profile-feed', params=params),
        )

    @contract(('GET', '/profile-feed'))
    def test_profile_feed_of_unknown_user(self, browser):
        response = browser.get('/profile-feed', params={'u': 9999999}, status=404)
        check_snapshot('profile_feed_unknown_user', response)

    @contract(('GET', '/profile-feed'))
    def test_profile_feed_without_user(self, browser):
        response = browser.get('/profile-feed', status=422)
        check_snapshot('profile_feed_without_user', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['u']


@pytest.mark.usefixtures('documents')
class TestSitemaps:
    @contract(('GET', '/sitemaps'), ('GET', '/sitemaps/{doc_type}/{i}'))
    def test_sitemaps(self, browser):
        check_snapshot('sitemaps', browser.get('/sitemaps'))
        check_snapshot('sitemaps_waypoints', browser.get('/sitemaps/w/0'))

    @contract(('GET', '/sitemaps.xml'), ('GET', '/sitemaps.xml/{doc_type}/{i}.xml'))
    def test_sitemaps_xml(self, browser):
        index = browser.get('/sitemaps.xml')
        check_snapshot('sitemaps_xml', index)
        assert b'<sitemapindex' in index.body
        waypoints = browser.get('/sitemaps.xml/w/0.xml')
        check_snapshot('sitemaps_xml_waypoints', waypoints)
        assert b'<urlset' in waypoints.body

    @contract(('GET', '/sitemaps'), ('GET', '/sitemaps.xml'))
    def test_not_modified(self, browser):
        for url, name in [('/sitemaps', 'sitemaps'), ('/sitemaps.xml', 'sitemaps_xml')]:
            etag = browser.get(url).headers['ETag']
            response = browser.get(url, headers={'If-None-Match': etag}, status=304)
            check_snapshot(f'{name}_not_modified', response)

    @contract(('GET', '/sitemaps/{doc_type}/{i}'))
    def test_invalid_page(self, browser):
        response = browser.get('/sitemaps/z/1', status=422)
        check_snapshot('sitemaps_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['doc_type']
        # a page that is not a number: not found
        browser.get('/sitemaps/w/x', status=404)

    @contract(('GET', '/sitemaps.xml/{doc_type}/{i}.xml'))
    def test_invalid_page_xml(self, browser):
        response = browser.get('/sitemaps.xml/z/1.xml', status=422)
        check_snapshot('sitemaps_xml_invalid', response)
        assert [name for _, name, _ in invalid_parameters(response)] == ['doc_type']
        browser.get('/sitemaps.xml/w/x.xml', status=404)

    @contract(
        ('GET', '/sitemaps/{doc_type}/{i}'), ('GET', '/sitemaps.xml/{doc_type}/{i}.xml')
    )
    def test_page_without_documents(self, browser):
        check_snapshot(
            'sitemaps_empty_page',
            browser.get('/sitemaps/w/99', status=404),
        )
        response = browser.get('/sitemaps.xml/w/99.xml', status=404)
        check_snapshot('sitemaps_xml_empty_page', response)


@pytest.mark.usefixtures('documents')
class TestCoverageLookup:
    @contract(('GET', '/getcoverage'))
    def test_coverage_of_a_point(self, browser):
        response = browser.get('/getcoverage', params={'lon': 5.71, 'lat': 45.655})
        check_snapshot('getcoverage', response)

    @contract(('GET', '/getcoverage'))
    def test_no_coverage(self, browser):
        response = browser.get('/getcoverage', params={'lon': 0, 'lat': 0})
        check_snapshot('getcoverage_none', response)
        assert response.json is None

    @contract(('POST', '/getpolygoncoverage'))
    def test_coverages_of_a_polygon(self, browser):
        response = browser.post('/getpolygoncoverage', {'geom_detail': POLYGON_4326})
        check_snapshot('getpolygoncoverage', response)


@pytest.mark.usefixtures('documents')
class TestImageRoutes:
    @contract(('POST', '/images/list'))
    def test_create_a_list(self, browser, documents):
        image = {
            'filename': 'list.jpg',
            'activities': ['hiking'],
            'image_type': 'collaborative',
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'From a list'}],
            'associations': {
                'waypoints': [{'document_id': documents.ids['waypoints']}]
            },
        }
        with patch(
            'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
        ):
            response = browser.post(
                '/images/list',
                {'images': [image]},
                user='contributor',
            )
        check_snapshot('images_list', response)

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy(self, browser, documents):
        response = browser.get(
            f'/images/proxy/{documents.ids["images"]}',
            params={'size': 'MI'},
            status=302,
        )
        check_snapshot('images_proxy', response)

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy_original(self, browser, documents):
        response = browser.get(f'/images/proxy/{documents.ids["images"]}', status=302)
        check_snapshot('images_proxy_original', response)
        assert response.body.startswith(b'302 Found\n\nThe resource was found at ')

    @contract(('GET', '/images/proxy/{id}'))
    def test_proxy_errors(self, browser, documents):
        check_snapshot(
            'images_proxy_unknown',
            browser.get('/images/proxy/9999999', status=404),
        )
        response = browser.get(
            f'/images/proxy/{documents.ids["images"]}',
            params={'size': 'XX'},
            status=400,
        )
        check_snapshot('images_proxy_invalid_size', response)
        assert [e['name'] for e in response.json['errors']] == ['size']
