import asyncio

from anyio import to_thread
from webtest import TestApp

from c2corg_api.app import Application, Registry, create_fastapi_app, threads


def _client():
    return TestApp(Application(create_fastapi_app({})))


class TestApplication:
    def test_registry(self):
        registry = Registry({'a': '1'}, queue_config='queues')
        app = Application(create_fastapi_app({'a': '1'}, registry))
        assert app.registry is registry
        assert app.registry.settings == {'a': '1'}
        assert app.registry.queue_config == 'queues'

    def test_no_generated_docs(self):
        client = _client()
        for path in ('/docs', '/redoc', '/openapi.json'):
            client.get(path, status=404)

    def test_unknown_route(self):
        response = _client().get('/nothing/here', status=404)
        assert response.json == {
            'status': 'error',
            'errors': [
                {
                    'location': 'body',
                    'name': 'Not Found',
                    'description': '/nothing/here',
                }
            ],
        }

    def test_method_not_allowed(self):
        response = _client().delete('/health', status=405)
        assert response.json == {
            'status': 'error',
            'errors': [
                {'location': 'body', 'name': 'Method Not Allowed', 'description': None}
            ],
        }

    def test_ids_that_are_not_numbers_reach_the_route(self):
        # its validators answer them (invalid id), as on Pyramid
        response = _client().get('/images/proxy/abc', status=400)
        assert response.json['errors'] == [
            {'location': 'querystring', 'name': 'id', 'description': 'invalid id'}
        ]

    def test_fixed_path_is_not_an_id(self):
        # /routes/{id} has a PUT, the fixed path has not
        path = '/routes/update_public_transportation_rating'
        response = _client().put(path, status=405)
        assert response.json['errors'][0]['name'] == 'Method Not Allowed'


class TestUnexpectedError:
    def test_logged_and_answered_like_pyramid(self, caplog):
        fastapi_app = create_fastapi_app({})

        @fastapi_app.get('/boom')
        def boom():
            raise RuntimeError('boom')

        client = TestApp(Application(fastapi_app))
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


class TestThreads:
    def test_the_setting(self):
        assert threads({'server.threads': '3', 'sqlalchemy.pool_size': '5'}) == 3

    def test_the_database_pool_by_default(self):
        assert threads({'sqlalchemy.pool_size': '7'}) == 7

    def test_the_database_pool_if_empty(self):
        assert threads({'server.threads': '', 'sqlalchemy.pool_size': '7'}) == 7

    def test_without_settings(self):
        assert threads({}) == 5

    def test_applied_when_the_app_starts(self):
        app = create_fastapi_app({'server.threads': '3'})

        async def tokens_while_running():
            async with app.router.lifespan_context(app):
                return to_thread.current_default_thread_limiter().total_tokens

        assert asyncio.run(tokens_while_running()) == 3
