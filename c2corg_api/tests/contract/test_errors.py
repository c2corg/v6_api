import datetime
from unittest.mock import patch

from c2corg_api.models.user import User
from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_documents import POINT, DocumentContractTest

WAYPOINT = {
    'waypoint_type': 'summit',
    'elevation': 3779,
    'geometry': {'geom': POINT},
    'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
}


class TestErrors(DocumentContractTest):
    """The error responses, in the Cornice shape {status, errors: [...]}."""

    @contract(('POST', '/waypoints'))
    def test_invalid_body(self):
        body = dict(WAYPOINT, locales=[{'lang': 'en'}], waypoint_type='nothing')
        response = self.post('/waypoints', body, user='contributor', status=400)
        check_snapshot('error_invalid_body', response)
        names = {error['name'] for error in response.json['errors']}
        assert names == {'locales.0.title', 'waypoint_type'}
        assert {e['location'] for e in response.json['errors']} == {'body'}

    @contract(('GET', '/waypoints'))
    def test_invalid_querystring(self):
        response = self.get('/waypoints', params={'offset': 'invalid'}, status=400)
        check_snapshot('error_invalid_querystring', response)
        assert response.json['errors'][0]['location'] == 'querystring'

    @contract(('GET', '/waypoints/{id}'))
    def test_invalid_id(self):
        response = self.get('/waypoints/abc', status=400)
        check_snapshot('error_invalid_id', response)

    @contract(('GET', '/waypoints/{id}'))
    def test_unknown_document(self):
        check_snapshot('error_not_found', self.get('/waypoints/9999999', status=404))

    @contract(('GET', '/waypoints/{id}/{lang}/info'))
    def test_info_of_a_missing_locale(self):
        # not an error: the info falls back to an existing locale
        response = self.get(self.url('waypoints', '/de/info'))
        check_snapshot('waypoints_info_fallback', response)
        assert response.json['locales'][0]['lang'] == 'en'

    def test_unknown_route(self):
        # not a route of the API: the answer of the web framework itself
        response = self.get('/no-such-route', status=404)
        check_snapshot('error_unknown_route', response)
        assert response.json['errors'] == [
            {'location': 'body', 'name': 'Not Found', 'description': '/no-such-route'}
        ]
        # also for a CORS preflight
        response = self.request('OPTIONS', '/no-such-route', status=404)
        assert response.json['errors'][0]['description'] == '/no-such-route'
        # no redirection to the path without its trailing slash
        for path in ('/', '/books/', self.url('books', '/')):
            response = self.get(path, status=404)
            assert response.json['errors'][0]['description'] == path

    def test_method_not_allowed(self):
        # a route without a view for the method (not a route of routes.txt)
        check_snapshot(
            'error_method_not_allowed',
            self.request('DELETE', '/waypoints', status=405),
        )
        for method, path in (
            ('PATCH', '/waypoints'),
            ('DELETE', self.url('books')),
            ('GET', '/images/list'),
            # a fixed path, not a document id
            ('PUT', '/routes/update_public_transportation_rating'),
            ('POST', '/routes/update_public_transportation_rating'),
        ):
            response = self.request(method, path, status=405)
            assert response.json['errors'] == [
                {'location': 'body', 'name': 'Method Not Allowed', 'description': None}
            ]

    def test_invalid_ids(self):
        # the ids of the paths are numbers: anything else is an invalid id,
        # not an unknown route
        for method, path, name in (
            ('GET', '/books/abc', 'id'),
            ('GET', '/books/abc/en/info', 'id'),
            ('GET', '/books/abc/en/12', 'id'),
            ('GET', self.url('books', '/en/abc'), 'version_id'),
            ('GET', '/document/abc/history/en', 'id'),
            ('GET', '/images/proxy/abc', 'id'),
            ('GET', '/stopareas/abc', 'id'),
            ('GET', '/stopareas/abc/en/info', 'id'),
            ('GET', '/waypoints_stopareas/abc/en/info', 'id'),
        ):
            response = self.request(method, path, status=400)
            assert response.json['errors'] == [
                {
                    'location': 'querystring',
                    'name': name,
                    'description': f'invalid {name}',
                }
            ], path
        # the permission is checked first
        for method, path in (
            ('PUT', '/books/abc'),
            ('DELETE', '/documents/delete/abc'),
            ('DELETE', '/documents/delete/abc/en'),
            ('GET', '/users/following-user/abc'),
            ('GET', '/users/blocked/abc'),
        ):
            response = self.request(method, path, status=403)
            assert response.json['errors'][0]['name'] == 'Forbidden', path

    @contract(('PUT', '/maps/{id}'))
    def test_forbidden(self):
        document = self.get(self.url('maps')).json
        body = {'message': 'contract test', 'document': document}
        response = self.put(self.url('maps'), body, user='contributor', status=403)
        check_snapshot('error_forbidden', response)

    @contract(('PUT', '/waypoints/{id}'))
    def test_anonymous(self):
        body = {'message': 'contract test', 'document': {}}
        check_snapshot(
            'error_anonymous', self.put(self.url('waypoints'), body, status=403)
        )

    @contract(('POST', '/waypoints'))
    def test_invalid_token(self):
        response = self.post(
            '/waypoints',
            WAYPOINT,
            headers={'Authorization': 'JWT token="not-a-token"'},
            status=401,
        )
        check_snapshot('error_invalid_token', response)

    @contract(('POST', '/waypoints'))
    def test_invalid_token_from_another_origin(self):
        # the error answers carry the CORS headers (#720, #730), but only
        # for the allowed origins
        response = self.app.post_json(
            '/waypoints',
            WAYPOINT,
            headers={
                'Authorization': 'JWT token="not-a-token"',
                'Origin': 'https://evil.example.org',
            },
            status=401,
        )
        assert 'Access-Control-Allow-Origin' not in response.headers

    @contract(('GET', '/books/{id}'))
    def test_invalid_token_from_another_origin_on_a_read(self):
        # the token is checked before the origin, as on the writes above:
        # on a route served by FastAPI too
        response = self.app.get(
            '/books/1',
            headers={
                'Authorization': 'JWT token="not-a-token"',
                'Origin': 'https://evil.example.org',
            },
            status=401,
        )
        assert 'Access-Control-Allow-Origin' not in response.headers

    @contract(('GET', '/books/{id}'))
    def test_another_origin_with_an_invalid_lang(self):
        # the origin is the first validator: its error comes with the others
        response = self.app.get(
            '/books/1',
            params={'l': 'xx'},
            headers={'Origin': 'https://evil.example.org'},
            status=400,
        )
        assert [e['name'] for e in response.json['errors']] == ['Origin', 'lang']

    @contract(('POST', '/waypoints'))
    def test_rate_limited(self):
        user = self.session.get(User, self.global_userids['contributor'])
        user.ratelimit_reset = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=5
        )
        user.ratelimit_remaining = 0
        self.session.flush()
        with patch('c2corg_api.emails.email_service.EmailService._send_email'):
            response = self.post('/waypoints', WAYPOINT, user='contributor', status=429)
        check_snapshot('error_rate_limited', response)
