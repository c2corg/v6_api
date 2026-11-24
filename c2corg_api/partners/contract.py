"""Contract checks against the partner sites: shapes of their answers.

Shared by the CLI (`python -m c2corg_api.partners`) and the live tests. The
JSON answers of an adapter run are reduced to shapes (see `shapes.py`), per
endpoint, and compared with the shapes of the committed fixtures
(`fixtures/<source>/shape.json`). Only what the adapter reads
(`REQUIRED_PATHS`) can make the comparison fail; other differences are listed.
"""

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from c2corg_api.partners import shapes
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, FetchResult
from c2corg_api.partners.transport import HttpResponse, Transport

SHAPE_FILE = 'shape.json'
# lists longer than this are cut in the recorded fixtures
MAX_ITEMS = 30
# fields the adapters never read and that are not ours to republish: licensed
# texts and photos (skitour), comment texts and route media (gulliver)
DROPPED_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ('skitour', 'sorties'): ('conditions', 'recit', 'photos'),
    ('gulliver', 'commentglobal'): ('content',),
    ('gulliver', 'routes'): ('media',),
}


# request params that change from run to run: sent, but not recorded
VOLATILE_PARAMS: dict[str, tuple[str, ...]] = {'skitour': ('j',)}  # days back


def endpoint_of(url: str) -> str:
    """Return the endpoint name of a URL: its last path segment, in snake case."""
    segment = urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1]
    return re.sub(r'[^a-z0-9]+', '_', segment.lower()).strip('_') or 'index'


def _trim(value, drop):
    if isinstance(value, dict):
        return {k: _trim(v, drop) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [_trim(v, drop) for v in value[:MAX_ITEMS]]
    return value


def trim_data(source: str, endpoint: str, data):
    """Drop the fields we do not keep and cut the lists to `MAX_ITEMS`."""
    return _trim(data, DROPPED_FIELDS.get((source, endpoint), ()))


def trim_body(source: str, url: str, body: bytes) -> bytes:
    """`trim_data` on a JSON body; anything else is returned as is."""
    try:
        data = json.loads(body)
    except ValueError:  # includes bad UTF-8
        return body
    trimmed = trim_data(source, endpoint_of(url), data)
    return (json.dumps(trimmed, indent=1, ensure_ascii=False) + '\n').encode()


class CapturingTransport:
    """Wraps a transport and keeps the responses it served, in memory."""

    def __init__(self, inner: Transport):
        self.inner = inner
        self.responses: list[HttpResponse] = []

    @property
    def request_count(self) -> int:
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None) -> HttpResponse:
        response = self.inner.get(url, params=params, headers=headers)
        self.responses.append(response)
        return response


def run_adapter(
    adapter,
    transport: Transport,
    secrets: Mapping[str, str],
    since: datetime.date,
    now: datetime.datetime | None = None,
) -> FetchResult:
    """Run an adapter once, without cursor, with an in-memory lookup cache."""
    now = now or datetime.datetime.now(datetime.UTC)
    ctx = FetchContext(
        since=since,
        now=now,
        cursor=None,
        transport=transport,
        lookups=MemoryLookupCache(),
        secrets=secrets,
    )
    return adapter.fetch(ctx)


def captured_shapes(source: str, responses) -> dict[str, Any]:
    """Shape of the JSON answers (status 200), merged per endpoint."""
    out: dict[str, Any] = {}
    for response in responses:
        if response.status != 200:
            continue
        try:
            data = json.loads(response.body)
        except ValueError:
            continue
        endpoint = endpoint_of(response.url)
        one = shapes.shape(trim_data(source, endpoint, data))
        out[endpoint] = shapes.merge(out[endpoint], one) if endpoint in out else one
    return out


def build_shape_index(directory: Path) -> dict[str, Any]:
    """Shape of every JSON file (status 200) of a fixture directory, by file."""
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    source = manifest['source']
    index = {}
    for entry in manifest.get('entries', []):
        file = entry.get('file')
        if not file or int(entry.get('status', 200)) != 200:
            continue
        try:
            data = json.loads((directory / file).read_bytes())
        except ValueError:
            continue
        index[file] = shapes.shape(trim_data(source, endpoint_of(entry['url']), data))
    return dict(sorted(index.items()))


def write_shape_index(directory: Path) -> dict[str, Any]:
    """Write `shape.json` next to the manifest and return its content."""
    index = build_shape_index(directory)
    (Path(directory) / SHAPE_FILE).write_text(
        json.dumps(index, indent=1, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    return index


def fixture_shapes(directory: Path) -> dict[str, Any]:
    """Return the shapes of `shape.json`, merged per endpoint.

    Raises FileNotFoundError when there is no `shape.json`.
    """
    directory = Path(directory)
    index = json.loads((directory / SHAPE_FILE).read_text(encoding='utf-8'))
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    out: dict[str, Any] = {}
    for entry in manifest.get('entries', []):
        file = entry.get('file')
        if file not in index:
            continue
        endpoint = endpoint_of(entry['url'])
        one = index[file]
        out[endpoint] = shapes.merge(out[endpoint], one) if endpoint in out else one
    return out


# -- paths ('[].sommets[].latlon') ------------------------------------------

_TOKEN = re.compile(r'\[\]|[^.\[\]]+')


def _type_name(node) -> str:
    if isinstance(node, str):
        return node
    return 'list' if isinstance(node, list) else 'object'


def lookup(shape, path: str):
    """Find a path in a shape.

    Returns `('ok', types)`, `('missing', ())` or `('unchecked', ())`: the
    last when the path is under an empty list, so the sample cannot tell.
    A list at the top is entered even when the path does not start with `[]`.
    """
    tokens = _TOKEN.findall(path)
    found: set[str] = set()
    unchecked = False

    def walk(node, i):
        nonlocal unchecked
        alternatives = (
            [json.loads(a) for a in node['any_of']]
            if isinstance(node, dict) and 'any_of' in node
            else [node]
        )
        for alt in alternatives:
            if i == len(tokens):
                found.add(_type_name(alt))
            elif isinstance(alt, list):
                if tokens[i] == '[]' or i == 0:
                    if alt:
                        walk(alt[0], i + 1 if tokens[i] == '[]' else i)
                    else:
                        unchecked = True
            elif isinstance(alt, dict) and tokens[i] in alt:
                walk(alt[tokens[i]], i + 1)

    walk(shape, 0)
    if found:
        return 'ok', frozenset(found)
    return ('unchecked', ()) if unchecked else ('missing', ())


def _compatible(expected, actual) -> bool:
    """Whether two sets of types can describe the same field.

    `null` fits anything (an absent value says nothing about the type), and
    int and float are both numbers.
    """

    def norm(types):
        return {'number' if t in ('int', 'float') else t for t in types} - {'null'}

    a, b = norm(expected), norm(actual)
    return not a or not b or bool(a & b)


_RETYPED = re.compile(r'^~ (.+): (.+) -> (.+)$')


def _meaningful(line: str) -> bool:
    """Tell whether a `~` line is more than `null` added or dropped (noise)."""
    match = _RETYPED.match(line)
    if not match:
        return True
    old, new = (set(match.group(i).split('|')) - {'null'} for i in (2, 3))
    return old != new


@dataclass
class Report:
    """The comparison of one adapter run with the fixture shapes."""

    # endpoint -> `shapes.diff` lines (all differences, breaking or not)
    diff: dict[str, list[str]] = field(default_factory=dict)
    # required paths removed or retyped: the adapter would break
    problems: list[str] = field(default_factory=list)
    # required paths the sample cannot confirm (empty list, endpoint not hit)
    unchecked: list[str] = field(default_factory=list)

    @property
    def breaking(self) -> bool:
        return bool(self.problems)


def compare(adapter, expected: Mapping[str, Any], actual: Mapping[str, Any]) -> Report:
    """Compare the shapes of a run (`actual`) with the fixtures (`expected`)."""
    report = Report()
    for endpoint in sorted(set(expected) | set(actual)):
        if endpoint in expected and endpoint in actual:
            lines = shapes.diff(expected[endpoint], actual[endpoint])
            report.diff[endpoint] = [x for x in lines if _meaningful(x)]
    for endpoint, paths in sorted(adapter.REQUIRED_PATHS.items()):
        for path in paths:
            label = f'{endpoint}: {path}'
            if endpoint not in actual:
                report.unchecked.append(f'{label} (endpoint not requested)')
                continue
            status, types = lookup(actual[endpoint], path)
            if status == 'unchecked':
                report.unchecked.append(f'{label} (empty list in the sample)')
            elif status == 'missing':
                report.problems.append(f'{label} is missing')
            else:
                old_status, old_types = lookup(expected.get(endpoint, {}), path)
                if old_status == 'ok' and not _compatible(old_types, types):
                    report.problems.append(
                        f'{label} changed type: {"|".join(sorted(old_types))}'
                        f' -> {"|".join(sorted(types))}'
                    )
    return report
