import re

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
        # the ids of the paths are numbers: a path with anything else is not
        # found
        for path in ('/routes/abc', '/routes/-1', '/routes/1.5'):
            response = _client().get(path, status=404)
            assert response.json['errors'][0]['name'] == 'Not Found', path

    def test_invalid_langs(self):
        response = _client().get('/routes/1', params={'l': 'xx'}, status=400)
        assert response.json['errors'] == [_error('lang', 'invalid lang')]
        response = _client().get('/routes/1', params={'cook': 'xx'}, status=400)
        assert response.json['errors'] == [_error('cook', 'invalid lang')]

    def test_info_and_version(self):
        # the languages of the paths, and the version ids
        for path in ('/routes/1/xx/info', '/routes/1/xx/12'):
            response = _client().get(path, status=400)
            assert response.json['errors'] == [_error('lang', 'invalid lang')], path
        # ids and version ids that are not numbers: not found
        for path in ('/routes/abc/en/info', '/routes/1/en/abc', '/routes/1/en/-2'):
            _client().get(path, status=404)

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
            _error('Forbidden', 'Authentication required', 'body')
        ]

    def test_feeds(self):
        # an invalid pagination token, not a secret
        params = {'pl': 'xx', 'limit': 'x', 'token': '12'}  # nosec B105
        response = _client().get('/feed', params=params, status=400)
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
        # an invalid pagination token, not a secret
        params = {'token': '1,2', 'u': 'x'}  # nosec B105
        response = _client().get('/documents/changes', params=params, status=400)
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
        response = _client().get('/document/1/history/xx', status=400)
        assert response.json['errors'] == [_error('lang', 'invalid lang')]
        _client().get('/document/abc/history/en', status=404)

    def test_search(self):
        response = _client().get(
            '/search', params={'q': 'x', 'limit': 'many', 'pl': 'xx'}, status=400
        )
        assert response.json['errors'] == [
            _error('limit', 'invalid limit'),
            _error('lang', 'invalid lang'),
        ]

    def test_sitemaps(self):
        for path in ('/sitemaps/zz/1', '/sitemaps.xml/zz/1.xml'):
            response = _client().get(path, status=400)
            assert response.json['errors'] == [
                _error('doc_type', 'invalid doc_type')
            ], path
        # a page that is not a number: not found
        for path in ('/sitemaps/w/-1', '/sitemaps.xml/w/x.xml'):
            _client().get(path, status=404)

    def test_stopareas(self):
        response = _client().get(
            '/stopareas', params={'page_id': '0', 'nb_items': 'x'}, status=400
        )
        assert response.json['errors'] == [
            _error('page_id', 'invalid page_id'),
            _error('nb_items', 'invalid nb_items'),
        ]
        for path in ('/waypoints/x/stopareas', '/waypoints/x/isReachable'):
            _client().get(path, status=404)
        response = _client().get('/reachableroutes', params={'offset': 'x'}, status=400)
        assert response.json['errors'] == [_error('offset', 'invalid offset')]

    def test_users(self):
        # the permission before the parameters, as Pyramid did
        for path in ('/users/preferences?pl=xx', '/users/following-user/1'):
            response = _client().get(path, status=403)
            assert response.json['errors'][0]['name'] == 'Forbidden', path
        # the content type before the permission, as Cornice did
        response = _client().get(
            '/users/blocked/1', headers={'Content-Type': 'text/plain'}, status=415
        )
        assert response.json['errors'][0]['name'] == 'Content-Type'

    def test_permission_texts(self):
        # the 403 answers say which permission the route requires
        response = _client().get('/users/preferences', status=403)
        assert response.json['errors'][0]['description'] == 'Authentication required'
        response = _client().get('/users/blocked/1', status=403)
        assert response.json['errors'][0]['description'] == 'Moderator role required'

    def test_coverage_of_a_point(self):
        response = _client().get('/getcoverage', params={'lon': 'nan'}, status=400)
        assert response.json['errors'] == [
            _error('lon', 'invalid lon'),
            _error('lat', 'invalid lat'),
        ]

    def test_image_proxy(self):
        # still checked by the validators of the view: the extension depends
        # on the size
        response = _client().get(
            '/images/proxy/1', params={'size': 'XL', 'extension': 'gif'}, status=400
        )
        assert response.json['errors'] == [
            _error('size', 'invalid size'),
            _error('extension', 'invalid extension'),
        ]

    def test_navitia(self):
        # the required parameters are only checked for their presence
        response = _client().get(
            '/navitia/journeys', params={'to': '', 'datetime': 'x'}, status=400
        )
        assert response.json['errors'] == [
            _error('from', 'Parameter from required'),
            _error('datetime_represents', 'Parameter datetime_represents required'),
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
        # other ids, nor the writes (not described yet)
        for path in ('/routes/{id}', '/routes/{id}/{lang}/info'):
            assert path in document['paths']
        assert '/routes/{id}/{lang}/{version_id}' in document['paths']
        # maps have no version route
        assert '/maps/{id}/{lang}/{version_id}' not in document['paths']
        assert '/routes' in document['paths']
        # the writes without a body schema are not described yet
        assert '/users/logout' not in document['paths']
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
        assert set(document['paths']['/routes/{id}']) == {'get', 'put'}
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


class TestEveryReadDescribed:
    def test_routes(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        for path in (
            '/search',
            '/sitemaps/{doc_type}/{i}',
            '/sitemaps.xml/{doc_type}/{i}.xml',
            '/stopareas',
            '/waypoints/{waypoint_id}/stopareas',
            '/reachableroutes',
            '/users/following-user/{id}',
            '/getcoverage',
            '/images/proxy/{id}',
            '/navitia/journeys',
            '/navitia/journeyreachableroutes/result/{job_id}',
        ):
            assert path in document['paths'], path

    def test_navitia_parameters(self):
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        operation = document['paths']['/navitia/journeys']['get']
        parameters = {p['name']: p for p in operation['parameters']}
        assert parameters['from']['required'] is True
        assert parameters['wheelchair']['required'] is False

    def test_every_get_route(self):
        # all but a GET that writes, described with the writes later
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        app = create_fastapi_app({})
        paths = {
            re.sub(r':\w+}', '}', route.path)
            for route in app.router.routes
            if 'GET' in getattr(route, 'methods', ())
        }
        missing = paths - set(document['paths'])
        assert missing == {'/routes/update_public_transportation_rating'}


class TestOpenApiErrors:
    def test_400_not_422(self):
        # the API answers invalid parameters with a 400 and its envelope,
        # not FastAPI's 422 (until #2546)
        document = _client({'api.openapi': 'true'}).get('/openapi.json').json
        for path, operations in document['paths'].items():
            for method, operation in operations.items():
                assert '422' not in operation['responses'], (path, method)
        responses = document['paths']['/routes/{id}']['get']['responses']
        assert responses['400']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/Errors'
        }
        schemas = document['components']['schemas']
        assert 'HTTPValidationError' not in schemas
        assert schemas['Errors']['properties']['status']['enum'] == ['error']
        # a route without parameters can not be invalid
        assert '400' not in document['paths']['/health']['get']['responses']

    def test_envelope_matches_the_answers(self):
        response = _client().get('/routes/1', params={'l': 'xx'}, status=400)
        properties = (
            _client({'api.openapi': 'true'})
            .get('/openapi.json')
            .json['components']['schemas']['Errors']['properties']
        )
        assert set(response.json) == set(properties)
        assert set(response.json['errors'][0]) == set(
            properties['errors']['items']['properties']
        )


class TestWriteBodies:
    def _document(self):
        return _client({'api.openapi': 'true'}).get('/openapi.json').json

    def test_bodies_of_the_writes(self):
        document = self._document()
        operation = document['paths']['/books/{id}']['put']
        body = operation['requestBody']['content']['application/json']['schema']
        name = body['$ref'].split('/')[-1]
        schema = document['components']['schemas'][name]
        assert set(schema['properties']) == {'message', 'document'}
        assert operation['requestBody']['required'] is True
        # the path parameter of the route, the errors of the body and the
        # permission
        assert operation['parameters'] == [
            {
                'name': 'id',
                'in': 'path',
                'required': True,
                'schema': {'type': 'integer', 'minimum': 0},
            }
        ]
        assert {'400', '403'} <= set(operation['responses'])
        assert operation['operationId'] == 'update_book'

    def test_every_write_with_a_body_schema(self):
        # the writes whose view validates its body with a schema
        # (schemas.base.body_validator)
        from fastapi.routing import APIRoute

        document = self._document()
        app = create_fastapi_app({})
        for route in app.router.routes:
            if not isinstance(route, APIRoute):
                continue
            schema = getattr(route.endpoint, 'body_schema', None)
            path = re.sub(r':\w+}', '}', route.path)
            if schema is not None and path in document['paths']:
                for method in route.methods:
                    operation = document['paths'][path][method.lower()]
                    assert 'requestBody' in operation, (path, method)

    def test_geometries(self):
        schemas = self._document()['components']['schemas']
        geometries = [
            prop
            for schema in schemas.values()
            for name, prop in schema.get('properties', {}).items()
            if name in ('geom', 'geom_detail')
        ]
        assert geometries
        assert all('GeoJSON' in prop['description'] for prop in geometries)


class TestDocumentResponses:
    def _document(self):
        return _client({'api.openapi': 'true'}).get('/openapi.json').json

    def _schema(self, document, path):
        responses = document['paths'][path]['get']['responses']
        return responses['200']['content']['application/json']['schema']

    def test_answers_of_the_reads(self):
        document = self._document()
        for path, name in (
            ('/routes', 'Documents'),
            ('/routes/{id}', 'Document'),
            ('/routes/{id}/{lang}/{version_id}', 'Version'),
            ('/images', 'Documents'),
            ('/maps/{id}', 'Document'),
        ):
            assert self._schema(document, path) == {
                '$ref': f'#/components/schemas/{name}'
            }, path

    def test_license(self):
        schemas = self._document()['components']['schemas']
        assert schemas['Document']['properties']['license'] == {
            '$ref': '#/components/schemas/License'
        }
        # the other fields of a document depend on its type
        assert schemas['Document']['additionalProperties'] is True
        assert set(schemas['License']['properties']) == {
            'id',
            'url',
            'attribution_url',
        }
        assert schemas['License']['type'] == ['object', 'null']

    def test_other_reads_left_open(self):
        # the info of a document is not a document
        document = self._document()
        assert self._schema(document, '/routes/{id}/{lang}/info') == {}
