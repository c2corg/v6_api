"""The shape of a JSON-like value, and the difference between two shapes.

Used to notice when a partner site changes the structure of what it sends.
"""

import json


def shape(value):
    """Return the shape of a JSON value: its keys and value types.

    Same output as `c2corg_api.tests.contract.shape`: keys sorted, types
    `null/bool/int/float/str`, the items of a list merged into one.
    """
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


def _plain(alternative):
    """Unquote an `any_of` alternative that is a plain type name."""
    value = json.loads(alternative)
    return value if isinstance(value, str) else alternative


def _flatten(node, path, out):
    if isinstance(node, dict) and 'any_of' not in node:
        if not node:
            out[path or '.'] = '{}'
        for key, child in node.items():
            _flatten(child, f'{path}.{key}' if path else key, out)
    elif isinstance(node, list):
        if node:
            _flatten(node[0], f'{path}[]', out)
        else:
            out[path or '.'] = '[]'
    elif isinstance(node, dict):
        out[path or '.'] = '|'.join(_plain(a) for a in node['any_of'])
    else:
        out[path or '.'] = str(node)


def diff(old, new) -> list[str]:
    """Return the differences between two shapes, one line per path.

    `+ path: type` for a new path, `- path` for a removed one and
    `~ path: old -> new` for a changed type. List items are written `[]`.
    """
    flat_old: dict[str, str] = {}
    flat_new: dict[str, str] = {}
    _flatten(old, '', flat_old)
    _flatten(new, '', flat_new)
    lines = []
    for path in sorted(set(flat_old) | set(flat_new)):
        if path not in flat_old:
            lines.append(f'+ {path}: {flat_new[path]}')
        elif path not in flat_new:
            lines.append(f'- {path}')
        elif flat_old[path] != flat_new[path]:
            lines.append(f'~ {path}: {flat_old[path]} -> {flat_new[path]}')
    return lines
