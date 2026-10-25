"""Check that a Pydantic schema validates exactly like the Colander one it replaces.

The cases are generated from the Colander schema tree: a minimal and a full
valid body, then, for every field, the body with that field removed, null,
of another type, too long, not one of its choices...
"""

import copy
import json
import math

import colander
from cornice.validators._colander import _none_to_null
from geoalchemy2 import WKBElement

from c2corg_api.ext.colander_ext import Geometry as ColanderGeometry
from c2corg_api.schemas.base import validate

# a valid GeoJSON geometry of each type, and a 4D point (GPS tracks)
GEOMETRIES = {
    'POINT': {'type': 'Point', 'coordinates': [635956, 5723604]},
    'LINESTRING': {'type': 'LineString', 'coordinates': [[0, 0, 1, 2], [1, 1, 2, 3]]},
    'MULTILINESTRING': {'type': 'MultiLineString', 'coordinates': [[[0, 0], [1, 1]]]},
    'POLYGON': {
        'type': 'Polygon',
        'coordinates': [[[0, 0], [0, 1], [1, 1], [0, 0]]],
    },
    'MULTIPOLYGON': {
        'type': 'MultiPolygon',
        'coordinates': [[[[0, 0], [0, 1], [1, 1], [0, 0]]]],
    },
}

WRONG_VALUES = [5, 1.5, True, 'x', '', [1], [], {'a': 1}]


def _choices(node):
    validator = node.validator
    validators = getattr(validator, 'validators', [validator])
    for v in validators:
        if isinstance(v, colander.OneOf):
            return list(v.choices)
    return None


def _max_length(node):
    validator = node.validator
    validators = getattr(validator, 'validators', [validator])
    for v in validators:
        if isinstance(v, colander.Length):
            return v.max
    return None


def sample(node, full):
    """Return a valid value for a node (all optional fields if `full`)."""
    typ = node.typ
    if isinstance(typ, colander.Mapping):
        return {
            child.name: sample(child, full)
            for child in node.children
            if full or child.required
        }
    if isinstance(typ, colander.Sequence):
        return [sample(node.children[0], full)]
    if isinstance(typ, ColanderGeometry):
        return json.dumps(GEOMETRIES[typ.geometry_types[0]])
    if isinstance(typ, colander.Integer):
        return 12
    if isinstance(typ, (colander.Date, colander.DateTime)):
        return '2016-01-01'
    if isinstance(typ, colander.Float):
        return 1.5
    if isinstance(typ, colander.Boolean):
        return True
    choices = _choices(node)
    if choices:
        return choices[-1]
    max_length = _max_length(node)
    return 'ab'[: max_length or 2]


def _variants(node):
    """Invalid or edge values of a node, besides removing it."""
    values = [None, *WRONG_VALUES]
    max_length = _max_length(node)
    if max_length:
        values += ['x' * max_length, 'x' * (max_length + 1)]
    if _choices(node):
        values.append('not-a-choice')
    if isinstance(node.typ, ColanderGeometry):
        values += [json.dumps(g) for g in GEOMETRIES.values()] + [
            '{"type": "Point", "coordinates": [1, 2, 3, 4]}',
            '{"type": "Point", "coordinates": [1, 2, 3, 4, 5]}',
            # mixed dimensions: geomet fails (a 500 today, on both sides)
            '{"type": "LineString", "coordinates": [[0, 0], [1, 1, 2, 3]]}',
            '{"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1]]]}',
            'not json',
            '{"type": "Feature"}',
        ]
    if isinstance(node.typ, colander.Sequence):
        values += [[None], [5], ['x'], [{}]]
    if isinstance(node.typ, colander.Float):
        values += ['1.5', '1e3', 'nan', 'inf', '-inf', 0, False, '0']
    if isinstance(node.typ, (colander.Date, colander.DateTime)):
        values += [
            '2016-1-1',
            '20160101',
            '2016',
            '2016-01',
            '201601',
            '2016-13-01',
            '2016-02-30',
            '01/01/2016',
            '2016-01-01T10:00:00',
            '2016-01-01T25:00:00',
            '2016-01-01T10:00:00+02:00',
            '2016-01-01T10:00:00+25:00',
            '2016-01-01 10:00Z',
            ' 2016-01-01',
        ]
    if isinstance(node.typ, colander.Boolean):
        values += ['false', 'FALSE', '0', 0, 'no', 'off', 1, 'true', False]
    return values


def _paths(node, prefix=()):
    """Yield (path, node) of every node below `node` (list items as index 0)."""
    for child in node.children:
        path = (*prefix, 0 if isinstance(node.typ, colander.Sequence) else child.name)
        yield path, child
        yield from _paths(child, path)


def _set(body, path, value, delete=False):
    target = body
    for part in path[:-1]:
        if isinstance(target, list) and not target:
            return None
        target = target[part]
        if not isinstance(target, (dict, list)):
            return None
    last = path[-1]
    if isinstance(target, list):
        if not target:
            return None
        if delete:
            del target[last]
        else:
            target[last] = value
    elif delete:
        target.pop(last, None)
    else:
        target[last] = value
    return body


def cases(node):
    """Return the bodies to compare, generated from the Colander schema."""
    full = sample(node, True)
    result = [sample(node, False), full, {}, [], 'x', None]
    for path, child in _paths(node):
        deleted = _set(copy.deepcopy(full), path, None, delete=True)
        if deleted is not None:
            result.append(deleted)
        for value in _variants(child):
            changed = _set(copy.deepcopy(full), path, value)
            if changed is not None:
                result.append(changed)
    return result


def _normalize(value):
    if value is colander.null:
        return None
    if isinstance(value, float) and math.isnan(value):
        return 'nan'
    if isinstance(value, WKBElement):
        return ('wkb', bytes(value.data), value.srid)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def colander_result(node, body):
    try:
        return _normalize(node.deserialize(_none_to_null(copy.deepcopy(body)))), {}
    except colander.Invalid as e:
        return None, e.asdict()
    except Exception as e:  # an unexpected error is a result too
        return 'exception', type(e).__name__


def pydantic_result(schema, body):
    try:
        validated, errors = validate(schema, copy.deepcopy(body))
    except Exception as e:
        return 'exception', type(e).__name__
    return _normalize(validated), dict(errors)


def assert_parity(colander_node, schema, extra_cases=()):
    """Assert both schemas give the same data or errors for every case."""
    differences = []
    all_cases = cases(colander_node) + list(extra_cases)
    for body in all_cases:
        expected = colander_result(colander_node, body)
        actual = pydantic_result(schema, body)
        if actual != expected:
            differences.append((body, expected, actual))
    assert not differences, (
        '\n\n'.join(
            f'body: {b!r}\ncolander: {e!r}\npydantic: {a!r}'
            for b, e, a in differences[:5]
        )
        + f'\n\n({len(differences)} of {len(all_cases)} cases differ)'
    )


def assert_document_type_parity(colander_schemas, schemas, document):
    """Assert a document type's schemas replace its Colander schemas exactly.

    `colander_schemas` and `schemas` are (create, update, base, listing);
    `document` is a model instance used to compare dictify and objectify.
    """
    from c2corg_api.views import serialize

    colander_create, colander_update, colander_base, colander_listing = colander_schemas
    create, update, base, listing = schemas
    assert_parity(colander_create, create)
    assert_parity(colander_update, update)
    assert serialize(base.dictify(document)) == serialize(
        colander_base.dictify(document)
    )
    assert serialize(listing.dictify(document)) == serialize(
        colander_listing.dictify(document)
    )
    data = colander_create.deserialize(
        _none_to_null(copy.deepcopy(sample(colander_create, True)))
    )
    assert serialize(base.dictify(base.objectify(data))) == serialize(
        colander_base.dictify(colander_base.objectify(data))
    )
