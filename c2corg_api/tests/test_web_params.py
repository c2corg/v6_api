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
        assert '/routes/{id}' in document['paths']
        assert '/routes' not in document['paths']
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
