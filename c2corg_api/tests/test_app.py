from webtest import TestApp

from c2corg_api.app import Dispatcher, create_fastapi_app


def _pyramid_app(environ, start_response):
    """Stand-in for the Pyramid application: says who answered."""
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b'pyramid']


_pyramid_app.registry = object()


class _Route:
    def __init__(self, prefix):
        self.prefix = prefix

    def match(self, path):
        return {} if path.startswith(self.prefix) else None


class _RoutesMapper:
    """Stand-in for the routes of Pyramid: it has /moved/... only."""

    def get_routes(self):
        return [_Route('/moved/')]


def _client(fastapi_enabled=True):
    fastapi_app = create_fastapi_app({})

    @fastapi_app.get('/moved/{id}')
    def get_moved(id: int):
        return {'app': 'fastapi', 'id': id}

    @fastapi_app.get('/only-fastapi')
    def get_only_fastapi():
        return {'app': 'fastapi'}

    _pyramid_app.routes_mapper = _RoutesMapper()
    return TestApp(
        Dispatcher(fastapi_app, _pyramid_app, fastapi_enabled=fastapi_enabled)
    )


class TestDispatcher:
    def test_moved_route_goes_to_fastapi(self):
        assert _client().get('/moved/3').json == {'app': 'fastapi', 'id': 3}

    def test_other_routes_go_to_pyramid(self):
        assert _client().get('/not-moved/3').text == 'pyramid'

    def test_disabled_fastapi_leaves_to_pyramid_its_routes(self):
        client = _client(fastapi_enabled=False)
        assert client.get('/moved/3').text == 'pyramid'
        # the routes Pyramid does not have stay on FastAPI (/health, /search)
        assert client.get('/only-fastapi').json == {'app': 'fastapi'}

    def test_other_methods_of_a_moved_path_go_to_pyramid(self):
        # a resource can move one method at a time
        assert _client().put('/moved/3').text == 'pyramid'

    def test_cors_preflight_goes_where_the_request_will(self):
        client = _client()
        to_fastapi = client.options(
            '/moved/3', headers={'Access-Control-Request-Method': 'GET'}, status='*'
        )
        assert to_fastapi.text != 'pyramid'
        to_pyramid = client.options(
            '/moved/3', headers={'Access-Control-Request-Method': 'PUT'}
        )
        assert to_pyramid.text == 'pyramid'

    def test_registry_is_pyramid_s(self):
        fastapi_app = create_fastapi_app({})
        assert Dispatcher(fastapi_app, _pyramid_app).registry is _pyramid_app.registry

    def test_no_generated_docs(self):
        client = _client()
        for path in ('/docs', '/redoc', '/openapi.json'):
            assert client.get(path).text == 'pyramid'


class TestUnexpectedError:
    def test_logged_and_answered_like_pyramid(self, caplog):
        fastapi_app = create_fastapi_app({})

        @fastapi_app.get('/boom')
        def boom():
            raise RuntimeError('boom')

        client = TestApp(Dispatcher(fastapi_app, _pyramid_app))
        response = client.get('/boom', status=500)
        assert response.json == {
            'status': 'error',
            'errors': [
                {
                    'location': 'body',
                    'name': 'unexpected error',
                    'description': 'please consult the server logs',
                }
            ],
        }
        assert 'Unexpected error: boom' in caplog.text
