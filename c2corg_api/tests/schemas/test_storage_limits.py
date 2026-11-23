"""The limits of the schema fields, against the columns they are stored in."""

# A value the column cannot store made the INSERT fail with a 500, e.g. a
# height difference of 35000 m in a smallint: the schemas reject it with a 422.

import importlib
import pkgutil

import pytest
from sqlalchemy import BigInteger, Enum, Integer, SmallInteger, String, inspect

import c2corg_api.schemas
from c2corg_api.schemas.base import ModelSchema, validate
from c2corg_api.schemas.outing import OutingCreateSchema
from c2corg_api.schemas.types import INTEGER, SMALLINT, IntRange

# the ranges of the integer column types, the narrowest type first
COLUMN_RANGES = [
    (SmallInteger, (SMALLINT.minimum, SMALLINT.maximum)),
    (BigInteger, (-(2**63), 2**63 - 1)),
    (Integer, (INTEGER.minimum, INTEGER.maximum)),
]


def _model_schemas():
    """Every ModelSchema of the schemas package, with their children."""
    found = {}

    def add(model_schema):
        if id(model_schema) in found:
            return
        found[id(model_schema)] = model_schema
        for child in model_schema.children.values():
            add(child)

    for module in pkgutil.iter_modules(c2corg_api.schemas.__path__):
        names = vars(importlib.import_module(f'c2corg_api.schemas.{module.name}'))
        for value in names.values():
            if isinstance(value, ModelSchema):
                add(value)
    return list(found.values())


def _stored_fields():
    """The (name, schema field, column) of the fields stored in a column."""
    for model_schema in _model_schemas():
        mapper = inspect(model_schema.model)
        for name, field in model_schema.schema.model_fields.items():
            if name in model_schema.children or name not in mapper.columns:
                continue
            label = f'{model_schema.schema.__name__}.{name}'
            yield pytest.param(field, mapper.columns[name], id=label)


def _spec(field, kind):
    specs = [m for m in field.metadata if type(m).__name__ == kind]
    return specs[0] if specs else None


@pytest.mark.parametrize(('field', 'column'), list(_stored_fields()))
def test_field_fits_its_column(field, column):
    column_type = column.type
    for type_, (minimum, maximum) in COLUMN_RANGES:
        if isinstance(column_type, type_):
            bounds = _spec(field, IntRange.__name__)
            assert bounds is not None, f'no range for a {column_type!r} column'
            assert minimum <= bounds.minimum
            assert bounds.maximum <= maximum
            return
    if isinstance(column_type, String) and not isinstance(column_type, Enum):
        if column_type.length is None:
            return
        spec = _spec(field, '_StrSpec')
        assert spec is not None, f'not a string for a {column_type!r} column'
        assert spec.max_length is not None, f'no limit for a {column_type!r}'
        assert spec.max_length <= column_type.length


def test_out_of_range_outing_is_a_422():
    body = {
        'activities': ['hiking'],
        'date_start': '2026-07-24',
        'date_end': '2026-08-20',
        'locales': [{'lang': 'fr', 'title': 'Trek'}],
        'height_diff_up': 35000,
    }
    validated, errors = validate(OutingCreateSchema, body)
    assert validated is None
    assert errors == [
        {
            'type': 'less_than_equal',
            'loc': ['body', 'height_diff_up'],
            'msg': 'Greater than maximum value 32767',
            'input': 35000,
            'ctx': {'le': 32767},
        }
    ]
    validated, errors = validate(OutingCreateSchema, {**body, 'height_diff_up': 32767})
    assert errors == []
