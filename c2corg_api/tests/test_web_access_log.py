import logging
import re

from a2wsgi import ASGIMiddleware
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from webtest import TestApp

from c2corg_api.web.access_log import AccessLogMiddleware


def _client():
    app = FastAPI()

    @app.get('/hello')
    def hello():
        return PlainTextResponse('hello', status_code=201)

    @app.get('/fails')
    def fails():
        raise RuntimeError('fails')

    app.add_middleware(AccessLogMiddleware)
    return TestApp(ASGIMiddleware(app))


def _records(caplog):
    return [r for r in caplog.records if r.name == 'c2corg_api.access']


class TestAccessLog:
    def test_a_line_per_request(self, caplog):
        caplog.set_level(logging.INFO, logger='c2corg_api.access')
        _client().get(
            '/hello?pl=fr&limit=3',
            headers={'Referer': 'https://www.example.org/', 'User-Agent': 'tests/1'},
            extra_environ={'REMOTE_ADDR': '198.51.100.7', 'REMOTE_PORT': '50000'},
            status=201,
        )
        [record] = _records(caplog)
        # the message of gunicorn's access log
        assert re.fullmatch(
            r'198\.51\.100\.7 - - \[\d\d/\w{3}/\d{4}:\d\d:\d\d:\d\d \+0000\] '
            r'"GET /hello\?pl=fr&limit=3 HTTP/1\.\d" 201 5 '
            r'"https://www\.example\.org/" "tests/1"',
            record.getMessage(),
        )
        # and its fields, for the JSON logs
        assert record.client_addr == '198.51.100.7'
        assert record.method == 'GET'
        assert record.path == '/hello'
        assert record.query == 'pl=fr&limit=3'
        assert record.status == 201
        assert record.size == 5
        assert record.duration_ms >= 0
        assert record.referer == 'https://www.example.org/'
        assert record.user_agent == 'tests/1'

    def test_without_client_address_and_headers(self, caplog):
        caplog.set_level(logging.INFO, logger='c2corg_api.access')
        _client().get('/hello', headers={'User-Agent': ''}, status=201)
        [record] = _records(caplog)
        assert record.client_addr == '-'
        assert record.referer == '-'
        assert record.query == ''
        assert '"GET /hello HTTP/1.' in record.getMessage()

    def test_unknown_route(self, caplog):
        caplog.set_level(logging.INFO, logger='c2corg_api.access')
        _client().get('/nothing', status=404)
        [record] = _records(caplog)
        assert record.status == 404

    def test_an_error_is_logged_as_500(self, caplog):
        caplog.set_level(logging.INFO, logger='c2corg_api.access')
        # the server answers 500; the middleware only sees the exception
        _client().get('/fails', status=500)
        [record] = _records(caplog)
        assert record.status == 500
        assert record.path == '/fails'
