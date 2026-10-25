"""Field types that validate like the Colander types they replace."""
# Each type converts and checks the raw value in a `BeforeValidator`, so the
# error a client gets is the Colander one (name and message), not Pydantic's.
#
# Colander also treats some values as missing: `null` (Cornice turned it into
# `colander.null`), and values each type considers empty (any falsy value for a
# string, '' or [] for an integer...). A missing value takes the default of the
# field, or is an error if the field is required. `Empty` records the rule of a
# type, and `Schema` removes the empty values of a mapping before validation,
# so the defaults apply. List items have no default: an empty item is missing.

import datetime
import math
import re
from decimal import Decimal
from functools import partial
from typing import Annotated, get_args

from pydantic import BeforeValidator
from pydantic_core import PydanticCustomError


class Empty:
    """Marker: when a value counts as missing for a field type."""

    def __init__(self, is_empty):
        self.is_empty = is_empty


def _required():
    return PydanticCustomError('missing', 'Required')


def _str_empty(value):
    return value is None or not value


def _int_empty(value):
    return value is None or (value != 0 and not value)


def _none(value):
    return value is None


def _to_int(value):
    """Convert like `colander.Integer`: `int(value)`, so 1.5 gives 1."""
    if _int_empty(value):
        raise _required()
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise PydanticCustomError(
            'not_a_number', '"{value}" is not a number', {'value': str(value)}
        ) from e


class _StrSpec:
    def __init__(self, max_length=None, choices=None):
        self.max_length = max_length
        self.choices = choices


def _check_str(value, info, spec, item=False):
    """Check like `colander.String` with a `Length` or `OneOf` validator."""
    if _str_empty(value):
        raise _required()
    if not isinstance(value, str):
        # Colander's own message, odd suffix included: the name of the node
        name = '' if item else info.field_name
        raise PydanticCustomError(
            'not_a_string',
            '{value} is not a string: {suffix}',
            {'value': str(value), 'suffix': str({name: ''})},
        )
    if spec.max_length is not None and len(value) > spec.max_length:
        raise PydanticCustomError(
            'too_long',
            'Longer than maximum length {max_length}',
            {'max_length': spec.max_length},
        )
    if spec.choices is not None and value not in spec.choices:
        raise PydanticCustomError(
            'not_one_of',
            '"{value}" is not one of {choices}',
            {'value': value, 'choices': ', '.join(spec.choices)},
        )
    return value


def _str_type(spec, item=False):
    return Annotated[
        str | None,
        Empty(_str_empty),
        spec,
        BeforeValidator(partial(_check_str, spec=spec, item=item)),
    ]


def _check_sequence(value, min_length=None):
    """Check like `colander.Sequence`: a list (a string is not one)."""
    if value is None:
        raise _required()
    if not isinstance(value, (list, tuple)):
        raise PydanticCustomError(
            'not_iterable', '"{value}" is not iterable', {'value': str(value)}
        )
    if min_length is not None and len(value) < min_length:
        raise PydanticCustomError(
            'too_short',
            'Shorter than minimum length {min_length}',
            {'min_length': min_length},
        )
    return list(value)


def check_mapping(value):
    """Check like `colander.Mapping`: a dict."""
    if value is None:
        raise _required()
    if not isinstance(value, dict):
        raise PydanticCustomError(
            'not_a_mapping',
            '"{value}" is not a mapping type: '
            'Does not implement dict-like functionality.',
            {'value': str(value)},
        )
    return value


Int = Annotated[int | None, Empty(_int_empty), BeforeValidator(_to_int)]


def Str(max_length=None):  # noqa: N802 (used like a type)
    """Return a string type limited to `max_length` characters."""
    return _str_type(_StrSpec(max_length=max_length))


def OneOf(choices):  # noqa: N802 (used like a type)
    """Return a string type limited to the given choices."""
    return _str_type(_StrSpec(choices=list(choices)))


def Seq(item, min_length=None):  # noqa: N802 (used like a type)
    """Return a list type of `item`, of at least `min_length` items."""
    specs = [arg for arg in get_args(item) if isinstance(arg, _StrSpec)]
    if specs:
        # the items of a list are unnamed nodes in Colander
        item = _str_type(specs[0], item=True)
    return Annotated[
        list[item] | None,
        Empty(_none),
        BeforeValidator(partial(_check_sequence, min_length=min_length)),
    ]


def Map(schema):  # noqa: N802 (used like a type)
    """Return a type for a nested schema."""
    return Annotated[schema | None, Empty(_none), BeforeValidator(check_mapping)]


# the date format of `iso8601.parse_date`, which `colander.Date` used
_ISO8601 = re.compile(
    r"""
    (?P<year>[0-9]{4})
    (
        (
            (-(?P<monthdash>[0-9]{1,2}))
            |
            (?P<month>[0-9]{2})
            (?!$)  # Don't allow YYYYMM
        )
        (
            (
                (-(?P<daydash>[0-9]{1,2}))
                |
                (?P<day>[0-9]{2})
            )
            (
                (
                    (?P<separator>[ T])
                    (?P<hour>[0-9]{2})
                    (:{0,1}(?P<minute>[0-9]{2})){0,1}
                    (
                        :{0,1}(?P<second>[0-9]{1,2})
                        ([.,](?P<second_fraction>[0-9]+)){0,1}
                    ){0,1}
                    (?P<timezone>
                        Z
                        |
                        (
                            (?P<tz_sign>[-+])
                            (?P<tz_hour>[0-9]{2})
                            :{0,1}
                            (?P<tz_minute>[0-9]{2}){0,1}
                        )
                    ){0,1}
                ){0,1}
            )
        ){0,1}  # YYYY-MM
    ){0,1}  # YYYY only
    $
    """,
    re.VERBOSE,
)


def _parse_datetime(value, default_tz=None):
    """Parse like `iso8601.parse_date`, which Colander used."""
    match = _ISO8601.match(value)
    if not match:
        raise ValueError(value)
    g = {k: v for k, v in match.groupdict().items() if v is not None}
    if 'tz_sign' in g:
        hours, minutes = int(g['tz_hour']), int(g.get('tz_minute', 0))
        sign = -1 if g['tz_sign'] == '-' else 1
        tz = datetime.timezone(sign * datetime.timedelta(hours=hours, minutes=minutes))
    elif g.get('timezone') == 'Z':
        tz = datetime.UTC
    else:
        tz = default_tz
    fraction = g.get('second_fraction', '0')
    result = datetime.datetime(
        year=int(g['year']),
        month=int(g.get('month', g.get('monthdash', 1))),
        day=int(g.get('day', g.get('daydash', 1))),
        hour=int(g.get('hour', 0)),
        minute=int(g.get('minute', 0)),
        second=int(g.get('second', 0)),
        microsecond=int(Decimal(f'0.{fraction}') * Decimal('1000000.0')),
        tzinfo=tz,
    )
    return result


def _date_empty(value):
    return value is None or not value


def _to_date(value):
    if _date_empty(value):
        raise _required()
    if isinstance(value, datetime.date):
        return value
    try:
        return _parse_datetime(value).date()
    except (ValueError, TypeError, ArithmeticError) as e:
        raise PydanticCustomError('invalid_date', 'Invalid date') from e


def _to_datetime(value):
    """Convert like `colander.DateTime` from ColanderAlchemy: ISO 8601."""
    # without a time zone, the datetime stays naive (ColanderAlchemy creates
    # the type without a default time zone)
    if _date_empty(value):
        raise _required()
    if isinstance(value, datetime.datetime):
        return value
    try:
        return _parse_datetime(value)
    except (ValueError, TypeError, ArithmeticError) as e:
        raise PydanticCustomError('invalid_date', 'Invalid date') from e


def _to_float(value):
    """Convert like `colander.Float`: `float(value)`."""
    if _int_empty(value):
        raise _required()
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise PydanticCustomError(
            'not_a_number', '"{value}" is not a number', {'value': str(value)}
        ) from e


def _to_finite_float(value):
    """Convert like `colander_ext.FiniteFloat`: NaN and infinity give null."""
    result = _to_float(value)
    return result if math.isfinite(result) else None


def _to_bool(value):
    """Convert like `colander.Boolean`: only 'false' and '0' are false."""
    if value is None:
        raise _required()
    return str(value).lower() not in ('false', '0')


Date = Annotated[datetime.date | None, Empty(_date_empty), BeforeValidator(_to_date)]
DateTime = Annotated[
    datetime.datetime | None, Empty(_date_empty), BeforeValidator(_to_datetime)
]
Float = Annotated[float | None, Empty(_int_empty), BeforeValidator(_to_float)]
FiniteFloat = Annotated[
    float | None, Empty(_int_empty), BeforeValidator(_to_finite_float)
]
Bool = Annotated[bool | None, Empty(_none), BeforeValidator(_to_bool)]
