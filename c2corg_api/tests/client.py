"""The HTTP client of the tests: FastAPI's TestClient, with WebTest's interface."""
# The tests were written for WebTest (on Pyramid, then through an ASGI-to-WSGI
# bridge). This adapter keeps the calls they make (get, post_json...,
# status=, expect_errors=) and drives the application as uvicorn does, through
# ASGI.

import json
from xml.etree import ElementTree  # nosec B405 (the API's own answers)

from starlette.testclient import TestClient


class AppError(AssertionError):
    """An unexpected status, as WebTest's AppError."""


class Response:
    """The answer to a request, with the attributes of WebTest's responses."""

    def __init__(self, response):
        self._response = response
        self.headers = response.headers
        self.status_int = self.status_code = response.status_code
        self.status = f'{response.status_code} {response.reason_phrase}'
        self.body = response.content
        self.text = response.text
        content_type = response.headers.get('Content-Type', '')
        self.content_type = content_type.split(';')[0].strip()

    @property
    def json(self):
        return self._response.json()

    json_body = json

    @property
    def xml(self):
        return ElementTree.fromstring(self.body)  # nosec B314 (the API's answer)


class Client:
    """A WebTest-like client of an ASGI application."""

    def __init__(self, app):
        self.app = app
        self._client = _test_client(app)

    @property
    def registry(self):
        """The settings and configuration of the application (queue_config...)."""
        return self.app.state.registry

    def __enter__(self):
        # runs the lifespan of the application, as uvicorn does
        self._client.__enter__()
        return self

    def __exit__(self, *exc):
        self._client.__exit__(*exc)

    def get(self, url, params=None, headers=None, **kwargs):
        return self._request('GET', url, params=params, headers=headers, **kwargs)

    def head(self, url, params=None, headers=None, **kwargs):
        return self._request('HEAD', url, params=params, headers=headers, **kwargs)

    def options(self, url, headers=None, **kwargs):
        return self._request('OPTIONS', url, headers=headers, **kwargs)

    def delete(self, url, params='', headers=None, **kwargs):
        return self._send('DELETE', url, params, headers, **kwargs)

    def post(self, url, params='', headers=None, **kwargs):
        return self._send('POST', url, params, headers, **kwargs)

    def put(self, url, params='', headers=None, **kwargs):
        return self._send('PUT', url, params, headers, **kwargs)

    def patch(self, url, params='', headers=None, **kwargs):
        return self._send('PATCH', url, params, headers, **kwargs)

    def post_json(self, url, params=None, **kwargs):
        return self._send_json('POST', url, params, **kwargs)

    def put_json(self, url, params=None, **kwargs):
        return self._send_json('PUT', url, params, **kwargs)

    def delete_json(self, url, params=None, **kwargs):
        return self._send_json('DELETE', url, params, **kwargs)

    def request(self, url, method='GET', body=None, headers=None, **kwargs):
        return self._request(method, url, content=body, headers=headers, **kwargs)

    def _send_json(self, method, url, params, headers=None, **kwargs):
        headers = {'Content-Type': 'application/json', **(headers or {})}
        content = json.dumps(params) if params is not None else ''
        return self._request(method, url, content=content, headers=headers, **kwargs)

    def _send(self, method, url, params, headers=None, content_type=None, **kwargs):
        # a string is the body, a dict a form; WebTest sends both as a form
        # unless told otherwise
        headers = dict(headers or {})
        if not any(name.lower() == 'content-type' for name in headers) and params:
            headers['Content-Type'] = (
                content_type or 'application/x-www-form-urlencoded'
            )
        if isinstance(params, dict):
            return self._request(method, url, data=params, headers=headers, **kwargs)
        return self._request(method, url, content=params, headers=headers, **kwargs)

    def _request(
        self,
        method,
        url,
        status=None,
        expect_errors=False,
        extra_environ=None,
        **kwargs,
    ):
        client = self._client
        if extra_environ:
            # the address of the client, the only part of the environ used
            client = _test_client(
                self.app,
                (extra_environ['REMOTE_ADDR'], int(extra_environ['REMOTE_PORT'])),
            )
        response = Response(client.request(method, url, **kwargs))
        _check_status(response, status, expect_errors)
        return response


def _test_client(app, address=None):
    # localhost and no client address, as with WebTest; no redirection
    # followed, and an unexpected error is answered with a 500, as by uvicorn
    return TestClient(
        app,
        base_url='http://localhost',
        client=address,
        follow_redirects=False,
        raise_server_exceptions=False,
    )


def _check_status(response, status, expect_errors):
    if status == '*':
        return
    if status is None:
        if expect_errors or response.status_int < 400:
            return
    elif response.status_int in (status if isinstance(status, list) else [status]):
        return
    raise AppError(
        f'Bad response: {response.status} (not {status or "2xx/3xx"})\n{response.text}'
    )
