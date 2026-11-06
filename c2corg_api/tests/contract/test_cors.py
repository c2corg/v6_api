import pytest

from c2corg_api.tests.contract import check_snapshot, contract

# the CORS headers, recorded for these tests only (they are the same for
# every route)
CORS_HEADERS = (
    'Access-Control-Allow-Headers',
    'Access-Control-Allow-Methods',
    'Access-Control-Max-Age',
    'X-Content-Type-Options',
)


@pytest.mark.usefixtures('client')
class TestCors:
    """CORS as the clients see it, on a public route (/health)."""

    def check(self, name, response):
        check_snapshot(f'cors_{name}', response, CORS_HEADERS)

    @contract(('GET', '/health'))
    def test_allowed_origin(self, browser):
        self.check('allowed_origin', browser.get('/health'))

    @contract(('GET', '/health'))
    def test_no_origin(self, browser):
        self.check('no_origin', browser.get('/health', headers={'Origin': None}))

    @contract(('GET', '/health'))
    def test_other_origin(self, browser):
        response = browser.get(
            '/health',
            headers={'Origin': 'https://evil.example.org'},
            status='*',
        )
        self.check('other_origin', response)
        assert response.json['errors'] == [
            {
                'location': 'header',
                'name': 'Origin',
                'description': 'https://evil.example.org not allowed',
            }
        ]

    @contract(('GET', '/health'))
    def test_head(self, browser):
        self.check('head', browser.request('HEAD', '/health'))

    def preflight(self, browser, status=200, **headers):
        return browser.request('OPTIONS', '/health', headers=headers, status=status)

    @contract(('GET', '/health'))
    def test_preflight(self, browser):
        response = self.preflight(browser, **{'Access-Control-Request-Method': 'GET'})
        self.check('preflight', response)

    @contract(('GET', '/health'))
    def test_preflight_with_headers(self, browser):
        response = self.preflight(
            browser,
            **{
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Authorization, Content-Type',
            },
        )
        self.check('preflight_with_headers', response)

    @contract(('GET', '/health'))
    def test_preflight_without_method(self, browser):
        response = self.preflight(browser, status='*')
        self.check('preflight_without_method', response)
        assert response.json['errors'] == [
            {
                'location': 'header',
                'name': 'Access-Control-Request-Method',
                'description': 'this header is mandatory',
            }
        ]

    @contract(('GET', '/health'))
    def test_preflight_other_origin(self, browser):
        response = self.preflight(
            browser,
            status='*',
            **{
                'Origin': 'https://evil.example.org',
                'Access-Control-Request-Method': 'GET',
            },
        )
        self.check('preflight_other_origin', response)
        assert response.json['errors'] == [
            {
                'location': 'header',
                'name': 'Origin',
                'description': 'https://evil.example.org not allowed',
            }
        ]
