"""The validation behaviours the schemas kept from Colander."""

import datetime
import json
import math

from c2corg_api.schemas.base import DROP, Schema, validate
from c2corg_api.schemas.geometry import Geometry
from c2corg_api.schemas.types import (
    Bool,
    Date,
    DateTime,
    FiniteFloat,
    Float,
    Int,
    Map,
    OneOf,
    Seq,
    Str,
    email_check,
    function_check,
)


class Item(Schema):
    document_id: Int


class Example(Schema):
    required: Str(5)
    text: Str(5) = None
    choice: OneOf(['a', 'b']) = 'a'
    number: Int = None
    items: Seq(Str()) = None
    non_empty: Seq(Str(), min_length=1) = None
    mapping: Map(Item) = None
    date: Date = None
    datetime: DateTime = None
    flag: Bool = None
    ratio: Float = None
    finite: FiniteFloat = None
    dropped: Str() = DROP
    checked: Str(
        min_length=3,
        checks=[email_check, function_check(lambda v: 'x' not in v, 'No x')],
    ) = None
    point: Geometry(['POINT']) = None


def _check(body):
    validated, errors = validate(Example, {'required': 'r', **body})
    return validated, dict(errors)


def _value(body, name):
    validated, errors = _check(body)
    assert errors == {}
    return validated[name]


def _error(body, name):
    validated, errors = _check(body)
    assert validated is None
    return errors[name]


class TestMissingValues:
    def test_required(self):
        assert dict(validate(Example, {})[1]) == {'required': 'Required'}
        for value in (None, '', 0, False, []):
            assert _error({'required': value}, 'required') == 'Required'

    def test_defaults(self):
        validated, _ = _check({})
        assert validated['choice'] == 'a'
        assert validated['text'] is None
        assert 'dropped' not in validated

    def test_empty_values_take_the_default(self):
        # any falsy value for a string, '' or [] for an integer, null for all
        assert _value({'text': ''}, 'text') is None
        assert _value({'text': 0}, 'text') is None
        assert _value({'number': ''}, 'number') is None
        assert _value({'number': []}, 'number') is None
        assert _value({'number': 0}, 'number') == 0
        assert _value({'choice': None}, 'choice') == 'a'
        assert _value({'items': []}, 'items') == []

    def test_empty_list_item_is_missing(self):
        assert _error({'items': [None]}, 'items.0') == 'Required'
        assert _error({'items': ['']}, 'items.0') == 'Required'


class TestConversions:
    def test_integer(self):
        assert _value({'number': '12'}, 'number') == 12
        assert _value({'number': 1.5}, 'number') == 1
        assert _value({'number': True}, 'number') == 1
        assert _error({'number': 'x'}, 'number') == '"x" is not a number'
        assert _error({'number': '1.5'}, 'number') == '"1.5" is not a number'

    def test_string(self):
        assert _error({'text': 12}, 'text') == "12 is not a string: {'text': ''}"
        assert _error({'items': [5]}, 'items.0') == "5 is not a string: {'': ''}"
        assert _error({'text': 'abcdef'}, 'text') == 'Longer than maximum length 5'
        assert _error({'choice': 'c'}, 'choice') == '"c" is not one of a, b'

    def test_choice_items(self):
        class Choices(Schema):
            items: Seq(OneOf(['a', 'b'])) = None

        _, errors = validate(Choices, {'items': ['a', 'c']})
        assert dict(errors) == {'items.1': '"c" is not one of a, b'}

    def test_sequence_and_mapping(self):
        assert _error({'items': 'abc'}, 'items') == '"abc" is not iterable'
        assert _error({'non_empty': []}, 'non_empty') == 'Shorter than minimum length 1'
        assert _error({'mapping': 'x'}, 'mapping') == (
            '"x" is not a mapping type: Does not implement dict-like functionality.'
        )
        assert _error({'mapping': {}}, 'mapping.document_id') == 'Required'

    def test_boolean(self):
        for value in ('false', 'FALSE', '0', 0, False):
            assert _value({'flag': value}, 'flag') is False
        for value in ('true', 'no', 'off', '', 1, True):
            assert _value({'flag': value}, 'flag') is True

    def test_dates(self):
        expected = datetime.date(2016, 1, 1)
        for value in ('2016-01-01', '2016-1-1', '20160101', '2016-01-01T10:00:00'):
            assert _value({'date': value}, 'date') == expected
        for value in ('2016-13-01', '01/01/2016', ' 2016-01-01', '2016-01-01T25:00'):
            assert _error({'date': value}, 'date') == 'Invalid date'
        assert _value({'datetime': '2016-01-01T10:00:00'}, 'datetime') == (
            datetime.datetime(2016, 1, 1, 10, 0)
        )
        aware = _value({'datetime': '2016-01-01T10:00:00+02:00'}, 'datetime')
        assert aware.utcoffset() == datetime.timedelta(hours=2)

    def test_floats(self):
        assert _value({'ratio': '1e3'}, 'ratio') == 1000.0
        assert math.isnan(_value({'ratio': 'nan'}, 'ratio'))
        assert _value({'finite': 'nan'}, 'finite') is None
        assert _value({'finite': 'inf'}, 'finite') is None
        assert _error({'ratio': [1]}, 'ratio') == '"[1]" is not a number'


class TestChecks:
    def test_all_messages_are_joined(self):
        assert _error({'checked': 'x'}, 'checked') == (
            'Shorter than minimum length 3; Invalid email address; No x'
        )
        assert _value({'checked': 'a@b.org'}, 'checked') == 'a@b.org'


class TestGeometry:
    def test_point(self):
        point = _value(
            {'point': json.dumps({'type': 'Point', 'coordinates': [1, 2]})}, 'point'
        )
        assert point.srid == 3857
        assert _value({'point': ''}, 'point') is None

    def test_4d_point(self):
        point = json.dumps({'type': 'Point', 'coordinates': [1, 2, 3, 4]})
        assert _value({'point': point}, 'point') is not None

    def test_invalid(self):
        five = json.dumps({'type': 'Point', 'coordinates': [1, 2, 3, 4, 5]})
        assert _error({'point': five}, 'point').startswith('Invalid geometry: ')
        assert _error({'point': 'not json'}, 'point') == 'Invalid geometry: not json'
        line = json.dumps({'type': 'LineString', 'coordinates': [[0, 0], [1, 1]]})
        assert _error({'point': line}, 'point') == (
            "Invalid geometry type. Expected: ['POINT']. Got: LINESTRING."
        )
