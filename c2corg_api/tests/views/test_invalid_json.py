import os
import re

import pytest

from c2corg_api.tests import auth_headers

pytestmark = pytest.mark.usefixtures('client')

ROUTES_FILE = os.path.join(os.path.dirname(__file__), '..', 'contract', 'routes.txt')


def _write_routes():
    """Return the (method, path) of the write routes of the API."""
    routes = []
    with open(ROUTES_FILE) as f:
        for line in f:
            method, path, _ = line.split()
            if method in ('POST', 'PUT', 'DELETE'):
                # any value for the path parameters: the body is invalid
                path = path.replace('{lang}', 'fr')
                routes.append((method, re.sub(r'\{\w+\}', '1', path)))
    return routes


# the write routes that do not read their body: they answer as without it
WITHOUT_BODY = {
    ('DELETE', '/documents/delete/1'),
    ('DELETE', '/documents/delete/1/fr'),
    ('POST', '/routes/update_public_transportation_rating'),
    ('POST', '/users/renew'),
    ('POST', '/users/validate_change_email/1'),
    ('POST', '/users/validate_register_email/1'),
}


@pytest.mark.parametrize(('method', 'path'), _write_routes())
def test_invalid_json_body(method, path, client):
    # a body that is not JSON is an error of the client, answered as
    # FastAPI does: a 422, not an unexpected error
    headers = auth_headers(username='moderator')
    headers['Content-Type'] = 'application/json'
    response = client.request(
        path, method=method, body=b'{not json', headers=headers, expect_errors=True
    )
    assert response.status_int != 500, response.body
    if (method, path) in WITHOUT_BODY:
        return
    assert response.status_int == 422, response.body
    # alone: the validators of the rules of the API need a valid body
    [error] = response.json['detail']
    assert error['type'] == 'json_invalid'
    assert error['loc'] == ['body', 1]
    assert error['msg'] == 'JSON decode error'
