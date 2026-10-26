"""API contract tests: what the clients of the API rely on, route by route."""

import json
import os

import pytest

from c2corg_api.tests.views import BaseTestRest

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')

# CONTRACT_UPDATE=1 writes the snapshots instead of comparing with them
UPDATE = os.environ.get('CONTRACT_UPDATE') == '1'

# the response headers a client can rely on (the others, like Date or
# Content-Length, change with every response)
CONTRACT_HEADERS = {
    'Access-Control-Allow-Credentials',
    'Access-Control-Allow-Origin',
    'Access-Control-Expose-Headers',
    'Cache-Control',
    'Content-Type',
    'ETag',
    'Location',
    'Vary',
}

# headers holding a list
LIST_HEADERS = {'Access-Control-Allow-Headers', 'Access-Control-Allow-Methods'}

# the (method, path) of the routes a contract test covers, as in routes.txt
COVERED = set()


def contract(*routes):
    """Mark a test as the contract test of the given (method, path) routes."""

    def mark(test):
        COVERED.update(routes)
        return test

    return mark


def shape(value):
    """Return the shape of a JSON value: its keys and value types."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, str):
        return 'str'
    if isinstance(value, dict):
        return {key: shape(value[key]) for key in sorted(value)}
    items = [shape(item) for item in value]
    if not items:
        return []
    merged = items[0]
    for item in items[1:]:
        merged = _merge(merged, item)
    return [merged]


def _merge(a, b):
    """Merge the shapes of two items of the same list."""
    if a == b:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        return {
            key: _merge(a[key], b[key])
            if key in a and key in b
            else a.get(key, b.get(key))
            for key in sorted(set(a) | set(b))
        }
    if isinstance(a, list) and isinstance(b, list):
        if not a or not b:
            return a or b
        return [_merge(a[0], b[0])]
    alternatives = {json.dumps(x, sort_keys=True) for x in (a, b)}
    for x in (a, b):
        if isinstance(x, dict) and 'any_of' in x:
            alternatives.discard(json.dumps(x, sort_keys=True))
            alternatives.update(x['any_of'])
    return {'any_of': sorted(alternatives)}


def response_contract(response, extra_headers=()):
    """Return what a client relies on in a response."""
    headers = {
        name: response.headers[name]
        for name in sorted(CONTRACT_HEADERS | set(extra_headers))
        if name in response.headers
    }
    # lists whose order is not part of the contract (Cornice builds some
    # from a set)
    for name in LIST_HEADERS & set(headers):
        headers[name] = ','.join(sorted(v.strip() for v in headers[name].split(',')))
    # the value of an ETag changes with the data, its presence does not
    if 'ETag' in headers:
        headers['ETag'] = '<etag>'
    result = {'status': response.status_int, 'headers': headers}
    if response.content_type == 'application/json' and response.body:
        result['body'] = shape(response.json)
    return result


def check_snapshot(name, response, extra_headers=()):
    """Compare the contract of a response with its snapshot."""
    path = os.path.join(SNAPSHOT_DIR, name + '.json')
    actual = response_contract(response, extra_headers)
    if UPDATE:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(actual, f, indent=2, sort_keys=True)
            f.write('\n')
        return
    if not os.path.exists(path):
        pytest.fail(f'no snapshot {name}.json: run with CONTRACT_UPDATE=1 to write it')
    with open(path) as f:
        expected = json.load(f)
    assert actual == expected


class ContractTest(BaseTestRest):
    """Base class of the contract tests: requests as a browser client sends them."""

    def request(self, method, url, body=None, user=None, status=200, **kwargs):
        """Send a request from an allowed CORS origin, as `user` if given."""
        headers = kwargs.pop('headers', {})
        # an allowed origin, unless the test gives one (None: no Origin)
        headers.setdefault('Origin', self.settings['cors.allowed_origins'].split()[0])
        if headers['Origin'] is None:
            del headers['Origin']
        if user:
            self.add_authorization_header(username=user, headers=headers)
        if body is None:
            call = getattr(self.app, method.lower())
            return call(url, headers=headers, status=status, **kwargs)
        call = getattr(self.app, method.lower() + '_json')
        return call(url, body, headers=headers, status=status, **kwargs)

    def get(self, url, user=None, status=200, **kwargs):
        return self.request('GET', url, user=user, status=status, **kwargs)

    def post(self, url, body, user=None, status=200, **kwargs):
        return self.request('POST', url, body, user=user, status=status, **kwargs)

    def put(self, url, body, user=None, status=200, **kwargs):
        return self.request('PUT', url, body, user=user, status=status, **kwargs)
