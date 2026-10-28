import os
import re

import pytest

from c2corg_api.tests.views import BaseTestRest

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
    ('POST', '/users/renew'),
    ('POST', '/users/validate_change_email/1'),
    ('POST', '/users/validate_register_email/1'),
}


class TestInvalidJson(BaseTestRest):
    @pytest.mark.parametrize(('method', 'path'), _write_routes())
    def test_invalid_json_body(self, method, path):
        # a body that is not JSON is an error of the client, answered as
        # Cornice does: a 400, not an unexpected error
        headers = self.add_authorization_header(username='moderator')
        headers['Content-Type'] = 'application/json'
        response = self.app.request(
            path, method=method, body=b'{not json', headers=headers, expect_errors=True
        )
        assert response.status_int != 500, response.body
        if (method, path) in WITHOUT_BODY:
            return
        assert response.status_int == 400, response.body
        # first: the views of outings and routes run more validators after it
        error = response.json['errors'][0]
        assert error['location'] == 'body'
        assert error['description'].startswith('Invalid JSON: ')
