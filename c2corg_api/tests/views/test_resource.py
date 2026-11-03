import json

import pytest

from c2corg_api.views.resource import JSON, Errors, extract_body, write


class _Request:
    """The part of a request extract_body reads."""

    def __init__(self, body, content_type='application/json'):
        self.body = body
        self.content_type = content_type
        self.errors = Errors()
        self.POST = {}

    @property
    def json_body(self):
        # as WebOb: a ValueError when the body is not JSON
        return json.loads(self.body)


class TestDeclarations:
    def test_write_keeps_its_checks(self):
        @write(validators=[len], permission='authenticated', json=True)
        def put_thing(request):
            pass

        assert put_thing.checks == ([len], 'authenticated', JSON)

    def test_defaults(self):
        @write()
        def post_thing(request):
            pass

        # no validator, no permission, any content type
        assert post_thing.checks == ([], None, None)


class TestErrors:
    def test_add(self):
        errors = Errors(403)
        errors.add('body', 'name', 'description')
        assert errors.status == 403
        assert errors == [
            {'location': 'body', 'name': 'name', 'description': 'description'}
        ]

    def test_unknown_location(self):
        with pytest.raises(ValueError):
            Errors().add('nowhere', 'name', 'description')


class TestExtractBody:
    def test_json_object(self):
        request = _Request(b'{"a": 1}')
        assert extract_body(request) == {'a': 1}
        assert request.errors == []

    def test_no_body(self):
        assert extract_body(_Request(b'')) == {}

    def test_invalid_json(self):
        request = _Request(b'{')
        assert extract_body(request) == {}
        assert request.errors[0]['description'].startswith('Invalid JSON: ')

    def test_not_an_object_or_an_array(self):
        request = _Request(b'"text"')
        assert extract_body(request) == {}
        assert request.errors == [
            {
                'location': 'body',
                'name': '',
                'description': 'Should be a JSON object or an array',
            }
        ]

    def test_not_json(self):
        assert extract_body(_Request(b'text', 'text/plain')) == b'text'
