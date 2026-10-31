from webtest import TestApp

from c2corg_api.app import Application, create_fastapi_app


def _client(settings=None):
    return TestApp(Application(create_fastapi_app(settings or {})))


def _error(name, description, location='querystring'):
    return {'location': location, 'name': name, 'description': description}


class TestTypedParameterErrors:
    # the answers of the validators of views/validation.py, which the typed
    # parameters replace: before the database is read
    def test_invalid_id(self):
        for path in ('/routes/abc', '/routes/-1', '/routes/1.5'):
            response = _client().get(path, status=400)
            assert response.json == {
                'status': 'error',
                'errors': [_error('id', 'invalid id')],
            }, path

    def test_invalid_langs(self):
        response = _client().get('/routes/abc', params={'l': 'xx'}, status=400)
        assert response.json['errors'] == [
            _error('id', 'invalid id'),
            _error('lang', 'invalid lang'),
        ]
        response = _client().get('/routes/1', params={'cook': 'xx'}, status=400)
        assert response.json['errors'] == [_error('cook', 'invalid lang')]

    def test_info_and_version(self):
        # the languages of the paths, and the version ids
        for path, errors in (
            ('/routes/abc/en/info', [_error('id', 'invalid id')]),
            ('/routes/1/xx/info', [_error('lang', 'invalid lang')]),
            (
                '/routes/abc/xx/12',
                [
                    _error('id', 'invalid id'),
                    _error('lang', 'invalid lang'),
                ],
            ),
            ('/routes/1/en/abc', [_error('version_id', 'invalid version_id')]),
            ('/routes/1/en/-2', [_error('version_id', 'invalid version_id')]),
        ):
            response = _client().get(path, status=400)
            assert response.json['errors'] == errors, path

    def test_listing(self):
        response = _client().get(
            '/routes', params={'offset': 'x', 'limit': '1.5', 'pl': 'xx'}, status=400
        )
        assert response.json['errors'] == [
            _error('offset', 'invalid offset'),
            _error('limit', 'invalid limit'),
            _error('lang', 'invalid lang'),
        ]

    def test_permission_first(self):
        # the listing of the profiles is for the authenticated users: the
        # permission is checked before the parameters, as Pyramid did
        response = _client().get('/profiles', params={'limit': 'x'}, status=403)
        assert response.json['errors'] == [
            _error(
                'Forbidden',
                'Unauthorized: UserProfileRest.collection_get__GET failed '
                'permission check',
                'body',
            )
        ]

    def test_feeds(self):
        response = _client().get(
            '/feed', params={'pl': 'xx', 'limit': 'x', 'token': '12'}, status=400
        )
        assert response.json['errors'] == [
            _error('lang', 'invalid lang'),
            _error('limit', 'invalid limit'),
            _error('token', 'invalid format'),
        ]
        # the user of a profile feed is required, and its error comes last
        response = _client().get('/profile-feed', params={'pl': 'xx'}, status=400)
        assert response.json['errors'] == [
            _error('lang', 'invalid lang'),
            _error('u', 'invalid u'),
        ]
        # the personal feed is for the authenticated users: before the
        # parameters
        response = _client().get('/personal-feed', params={'limit': 'x'}, status=403)
        assert response.json['errors'][0]['name'] == 'Forbidden'

    def test_histories(self):
        response = _client().get(
            '/documents/changes', params={'token': '1,2', 'u': 'x'}, status=400
        )
        assert response.json['errors'] == [
            _error('token', 'invalid format'),
            _error('u', 'invalid u'),
        ]
        response = _client().get(
            '/associations-history', params={'d': 'x', 'offset': 'y'}, status=400
        )
        assert response.json['errors'] == [
            _error('d', 'invalid d'),
            _error('offset', 'invalid offset'),
        ]
        response = _client().get('/document/abc/history/xx', status=400)
        assert response.json['errors'] == [
            _error('id', 'invalid id'),
            _error('lang', 'invalid lang'),
        ]

    def test_origin_first(self):
        response = _client().get(
            '/routes/1',
            params={'l': 'xx'},
            headers={'Origin': 'https://elsewhere.example'},
            status=400,
        )
        assert response.json['errors'] == [
            _error('Origin', 'https://elsewhere.example not allowed', 'header'),
            _error('lang', 'invalid lang'),
        ]


class TestOpenApi:
    def test_off_by_default(self):
        _client().get('/openapi.json', status=404)
        _client({'api.openapi': 'false'}).get('/openapi.json', status=404)

    def test_described_routes_only(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        assert document['info']['title'] == 'camptocamp.org API'
        # the document routes of each type, once: not the copies for the
        # other ids, nor the routes without typed parameters yet
        for path in ('/routes/{id}', '/routes/{id}/{lang}/info'):
            assert path in document['paths']
        assert '/routes/{id}/{lang}/{version_id}' in document['paths']
        # maps have no version route
        assert '/maps/{id}/{lang}/{version_id}' not in document['paths']
        assert '/routes' in document['paths']
        assert '/health' not in document['paths']
        assert all(':' not in path for path in document['paths'])

    def test_parameters(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        operation = document['paths']['/routes/{id}']['get']
        parameters = {p['name']: p for p in operation['parameters']}
        assert set(parameters) == {'id', 'l', 'cook', 'e'}
        assert parameters['id']['in'] == 'path'
        assert parameters['id']['schema']['type'] == 'integer'
        assert parameters['id']['schema']['minimum'] == 0
        # HEAD is not described: it answers as GET
        assert set(document['paths']['/routes/{id}']) == {'get'}
        assert 'en' in parameters['l']['schema']['anyOf'][0]['enum']
        assert parameters['cook']['in'] == 'query'

    def test_path_parameters(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        operation = document['paths']['/routes/{id}/{lang}/{version_id}']['get']
        parameters = {p['name']: p for p in operation['parameters']}
        assert set(parameters) == {'id', 'lang', 'version_id'}
        assert all(p['in'] == 'path' and p['required'] for p in parameters.values())
        assert 'en' in parameters['lang']['schema']['enum']
        assert parameters['version_id']['schema']['minimum'] == 0
        assert operation['operationId'] == 'get_routes_version'

    def test_listing_parameters(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        operation = document['paths']['/routes']['get']
        parameters = {p['name']: p for p in operation['parameters']}
        assert {'offset', 'limit', 'pl', 'q', 'bbox', 'sort'} < set(parameters)
        assert not any(p['required'] for p in parameters.values())
        assert operation['operationId'] == 'list_routes'

    def test_search_filters(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        operation = document['paths']['/waypoints']['get']
        parameters = {p['name']: p for p in operation['parameters']}
        # the typed parameters, then the filters of the waypoint search mapping
        assert {'offset', 'limit', 'pl', 'q', 'bbox', 'sort'} < set(parameters)
        assert parameters['wtyp']['schema']['items']['enum'][:1] == ['summit']
        assert parameters['wtyp']['explode'] is False
        assert parameters['plift']['schema'] == {'type': 'boolean'}
        assert (
            '`climbing_rating_min` and `climbing_rating_max`'
            in (parameters['crat']['description'])
        )
        # the filters differ by document type
        outings = document['paths']['/outings']['get']['parameters']
        assert 'date' in {p['name'] for p in outings}
        assert 'date' not in parameters


class TestSearchFilterParameters:
    def test_every_filter_described(self):
        from c2corg_api.search import search_documents
        from c2corg_api.web.search_parameters import search_filter_parameters

        for doc_type, search_model in search_documents.items():
            names = {p['name'] for p in search_filter_parameters(doc_type)}
            assert names == set(search_model.queryable_fields), doc_type

    def test_without_search_mapping(self):
        from c2corg_api.web.search_parameters import search_filter_parameters

        assert search_filter_parameters('v') == []


class TestTokens:
    def test_feed_token(self):
        from c2corg_api.web.params import _feed_token, _token

        parse = _token(_feed_token)
        assert parse('') is None
        id, time = parse('12,2026-10-31T10:00:00')
        assert id == 12
        assert time.year == 2026

    def test_changes_token(self):
        from c2corg_api.views.validation import parse_int_safe
        from c2corg_api.web.params import _token

        assert _token(parse_int_safe)('12') == 12
        assert _token(parse_int_safe)(None) is None
