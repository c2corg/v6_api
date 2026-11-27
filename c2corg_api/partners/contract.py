"""Contract checks against the partner sites: shapes of their answers.

Shared by the CLI (`python -m c2corg_api.partners`) and the live tests. The
JSON answers of an adapter run are reduced to shapes (see `shapes.py`), per
endpoint, and compared with the shapes of the committed fixtures
(`fixtures/<source>/shape.json`). Only what the adapter reads
(`REQUIRED_PATHS`) can make the comparison fail; other differences are listed.

`REQUIRED_PATHS` is also the allow-list of what a recording keeps: any other
field (licensed texts, comments, photos, tracks...) is dropped before it is
written, so a new free-text field of a partner never reaches the fixtures.

A source that publishes HTML declares `REQUIRED_SELECTORS` instead (endpoint ->
CSS selectors of every element it reads), with the same two roles: the
allow-list of a recording (`htmlparse.trim`) and the contract the live check
compares (a selector that matched in the fixtures must still match).
"""

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from c2corg_api.partners import htmlparse, shapes
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, FetchResult
from c2corg_api.partners.transport import HttpResponse, Transport

SHAPE_FILE = 'shape.json'
_TOKEN = re.compile(r'\[\]|[^.\[\]]+')
# a path token for any key of an object keyed by ids (`*.ID`: gulliver
# answers `{"350636": {...}, ...}`); its shape is `{"*": <merged values>}`
WILDCARD = '*'
LIST_ITEMS = '[]'  # the path token of the items of a list
# lists longer than this are cut in the recorded fixtures
MAX_ITEMS = 30


# request params that change from run to run: sent, but not recorded
VOLATILE_PARAMS: dict[str, tuple[str, ...]] = {'skitour': ('j',)}  # days back


def _adapter(source: str | None):
    from c2corg_api.partners.sources import REGISTRY

    return REGISTRY.get(source) if source else None


def endpoint_of(url: str, source: str | None = None) -> str:
    """Return the endpoint name of a URL: its last path segment, in snake case.

    A file extension is dropped, and so is an id with what follows it
    (`sortie-30061-belle-descente.html` is the endpoint `sortie`). An adapter
    whose endpoints share a last segment names them in `ENDPOINTS` (URL path
    suffix -> endpoint, e.g. gulliver `/front_page/comments`).
    """
    path = urlsplit(url).path.rstrip('/')
    for suffix, name in getattr(_adapter(source), 'ENDPOINTS', {}).items():
        if path.endswith(suffix.rstrip('/')):
            return name
    segment = path.rsplit('/', 1)[-1].lower()
    segment = re.sub(r'\.(?:php|html?|json)$', '', segment)
    if segment.isdigit():  # '/verhaeltnisse/2355428': the page of one item
        return 'detail'
    segment = re.sub(r'[-_]\d.*$', '', segment)
    return re.sub(r'[^a-z0-9]+', '_', segment).strip('_') or 'index'


def read_paths(source: str, endpoint: str) -> list[str]:
    """Return the JSON paths the adapter of a source reads from an endpoint.

    Empty for an unknown source or endpoint: nothing is kept of it.
    """
    from c2corg_api.partners.sources import REGISTRY

    adapter = REGISTRY.get(source)
    if adapter is None:
        return []
    return list(adapter.REQUIRED_PATHS.get(endpoint, ()))


def read_selectors(source: str, endpoint: str) -> list[str]:
    """Return the CSS selectors the adapter of a source reads from an HTML endpoint."""
    from c2corg_api.partners.sources import REGISTRY

    adapter = REGISTRY.get(source)
    if adapter is None:
        return []
    return list(getattr(adapter, 'REQUIRED_SELECTORS', {}).get(endpoint, ()))


def embedded_html(source: str, endpoint: str) -> dict[str, list[str]]:
    """Return the JSON paths of an endpoint holding HTML -> the selectors read in it.

    Some JSON answers carry an HTML fragment in a string (gulliver
    `front_page/comments`: `content`). The adapter declares the path in
    `REQUIRED_PATHS` and its selectors in `EMBEDDED_HTML`: the string is
    trimmed like an HTML page (`htmlparse.trim`) and its shape is the
    selectors that match.
    """
    adapter = _adapter(source)
    found = getattr(adapter, 'EMBEDDED_HTML', {}).get(endpoint, {})
    return {path: list(selectors) for path, selectors in found.items()}


def _map_path(data, tokens, fn):
    """Return `data` with `fn` applied to the values at a path (copied, not mutated)."""
    if not tokens:
        return fn(data)
    step, rest = tokens[0], tokens[1:]
    if isinstance(data, list) and step == LIST_ITEMS:
        return [_map_path(v, rest, fn) for v in data]
    if isinstance(data, dict) and step == WILDCARD:
        return {k: _map_path(v, rest, fn) for k, v in data.items()}
    if isinstance(data, dict) and step in data:
        return {**data, step: _map_path(data[step], rest, fn)}
    return data


def _on_embedded(source, endpoint, data, fn):
    """Apply `fn(text, selectors)` to each embedded HTML string of a JSON answer."""
    for path, selectors in embedded_html(source, endpoint).items():

        def one(value, selectors=selectors):
            return fn(value, selectors) if isinstance(value, str) else value

        data = _map_path(data, _TOKEN.findall(path), one)
    return data


def _tree(paths):
    """Turn paths into a nested dict; `{}` marks a path end (kept whole)."""
    root: dict = {}
    for path in paths:
        node = root
        for token in _TOKEN.findall(path):
            node = node.setdefault(token, {})
    return root


def _keep(value, tree):
    if not tree:  # end of a path: the value is read, keep it
        return value
    if isinstance(value, list):
        # a top-level list is entered even when the paths do not start with []
        sub = tree.get('[]', tree)
        return [_keep(v, sub) for v in value[:MAX_ITEMS]]
    if isinstance(value, dict) and WILDCARD in tree:
        # an object keyed by ids: every key, each value trimmed alike
        items = list(value.items())[:MAX_ITEMS]
        return {k: _keep(v, tree[WILDCARD]) for k, v in items}
    if isinstance(value, dict):
        return {k: _keep(v, tree[k]) for k, v in value.items() if k in tree}
    return None  # a scalar where the adapter expects an object: nothing read


def trim_data(source: str, endpoint: str, data):
    """Keep only the paths the adapter reads; cut the lists to `MAX_ITEMS`."""
    paths = read_paths(source, endpoint)
    if not paths:  # an endpoint the adapter does not declare: keep nothing
        return [] if isinstance(data, list) else {} if isinstance(data, dict) else None
    kept = _keep(data, _tree(paths))
    return _on_embedded(source, endpoint, kept, htmlparse.trim)


def pseudonymise_paths(source: str, endpoint: str) -> list[str]:
    """Return the JSON paths holding a partner user's identity (may be empty)."""
    from c2corg_api.partners.sources import REGISTRY

    adapter = REGISTRY.get(source)
    paths = getattr(adapter, 'PSEUDONYMISE_PATHS', {}) if adapter else {}
    return list(paths.get(endpoint, ()))


def _replace(value, tree, names):
    if not tree:
        if value is None or isinstance(value, bool | dict | list):
            return value
        fake = names.setdefault((type(value).__name__, value), len(names) + 1)
        return fake if isinstance(value, int) else f'user{fake}'
    if isinstance(value, list):
        sub = tree.get('[]', tree)
        return [_replace(v, sub, names) for v in value]
    if isinstance(value, dict) and WILDCARD in tree:
        return {k: _replace(v, tree[WILDCARD], names) for k, v in value.items()}
    if isinstance(value, dict):
        return {
            k: _replace(v, tree[k], names) if k in tree else v for k, v in value.items()
        }
    return value


def pseudonymise_data(source: str, endpoint: str, data, names: dict | None = None):
    """Replace the author identities by stable fakes ("user1", "user2"...).

    `names` is shared by the responses of one recording, so that the same
    author gets the same pseudonym everywhere. Integer ids stay integers.
    """
    paths = pseudonymise_paths(source, endpoint)
    if not paths:
        return data
    names = {} if names is None else names
    return _replace(data, _tree(paths), names)


REDACTED = re.compile(r'\[text \d+ chars\]')


def redacted(text: str) -> str:
    """Return the placeholder a recording writes instead of a partner text."""
    return f'[text {len(text)} chars]'


def redact_paths(source: str, endpoint: str) -> list[str]:
    """Return the JSON paths holding partner free text (may be empty).

    The adapter reads them (they are in `REQUIRED_PATHS`: the texts are stored
    in the database, never served), but a recording replaces each text by a
    placeholder (`[text 812 chars]`): no real partner text reaches a fixture.
    """
    adapter = _adapter(source)
    return list(getattr(adapter, 'REDACT_PATHS', {}).get(endpoint, ()))


def _redact_all(value):
    if isinstance(value, str):
        keep = not value.strip() or REDACTED.fullmatch(value)
        return value if keep else redacted(value)
    if isinstance(value, list):
        return [_redact_all(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_all(v) for k, v in value.items()}
    return value


def _redact(value, tree):
    if not tree:  # a text, or an object of texts: every string is replaced
        return _redact_all(value)
    if isinstance(value, list):
        sub = tree.get('[]', tree)
        return [_redact(v, sub) for v in value]
    if isinstance(value, dict) and WILDCARD in tree:
        return {k: _redact(v, tree[WILDCARD]) for k, v in value.items()}
    if isinstance(value, dict):
        return {k: _redact(v, tree[k]) if k in tree else v for k, v in value.items()}
    return value


def redact_data(source: str, endpoint: str, data):
    """Replace the texts at `REDACT_PATHS` by placeholders (`[text N chars]`)."""
    paths = redact_paths(source, endpoint)
    return _redact(data, _tree(paths)) if paths else data


def redact_selectors(source: str, endpoint: str) -> list[str]:
    """Return the CSS selectors of the elements holding partner free text."""
    adapter = _adapter(source)
    return list(getattr(adapter, 'REDACT_SELECTORS', {}).get(endpoint, ()))


def pseudonymise_selectors(source: str, endpoint: str) -> list[str]:
    """Return the CSS selectors of the elements holding a partner user's identity."""
    from c2corg_api.partners.sources import REGISTRY

    adapter = REGISTRY.get(source)
    selectors = getattr(adapter, 'PSEUDONYMISE_SELECTORS', {}) if adapter else {}
    return list(selectors.get(endpoint, ()))


def _decode_html(body: bytes) -> str:
    """Decode a page: UTF-8, else Windows-1252 (old sites in ISO-8859-1, on-ice.it).

    A recording is written in UTF-8 whatever the charset of the page.
    """
    try:
        return body.decode('utf-8')
    except UnicodeDecodeError:
        return body.decode('cp1252', errors='replace')


def trim_body(source: str, url: str, body: bytes, names: dict | None = None) -> bytes:
    """Trim a JSON body (`trim_data`, `pseudonymise_data`, `redact_data`) or HTML.

    An HTML body is trimmed (`htmlparse.trim`, with the pseudonyms of
    `PSEUDONYMISE_SELECTORS` and the placeholders of `REDACT_SELECTORS`) when
    the source declares selectors for the endpoint; anything else is returned
    as is.
    """
    try:
        data = json.loads(body)
    except ValueError:  # includes bad UTF-8
        endpoint = endpoint_of(url, source)
        selectors = read_selectors(source, endpoint)
        if selectors:
            return htmlparse.trim(
                _decode_html(body),
                selectors,
                pseudonymise_selectors(source, endpoint),
                names,
                redact=redact_selectors(source, endpoint),
            ).encode()
        return body
    endpoint = endpoint_of(url, source)
    trimmed = trim_data(source, endpoint, data)
    trimmed = pseudonymise_data(source, endpoint, trimmed, names)
    trimmed = redact_data(source, endpoint, trimmed)
    return (json.dumps(trimmed, indent=1, ensure_ascii=False) + '\n').encode()


def _shape(value, tree):
    """`shapes.shape`, with the objects keyed by ids (`*` paths) merged under `*`."""
    if isinstance(value, dict) and WILDCARD in tree:
        merged = None
        for child in value.values():
            one = _shape(child, tree[WILDCARD])
            merged = one if merged is None else shapes.merge(merged, one)
        return {WILDCARD: merged} if merged is not None else {}
    if isinstance(value, dict):
        return {k: _shape(value[k], tree.get(k, {})) for k in sorted(value)}
    if isinstance(value, list):
        items = [_shape(v, tree.get('[]', tree)) for v in value]
        if not items:
            return []
        merged = items[0]
        for item in items[1:]:
            merged = shapes.merge(merged, item)
        return [merged]
    return shapes.shape(value)


def data_shape(source: str, endpoint: str, data):
    """Return the shape of a (trimmed) JSON answer of an endpoint.

    Objects keyed by ids have the shape `{"*": ...}`, and an embedded HTML
    string the selectors that match in it (`{selector: "str"}`).
    """
    view = _on_embedded(source, endpoint, data, htmlparse.matches)
    return _shape(view, _tree(read_paths(source, endpoint)))


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
        endpoint = endpoint_of(response.url, source)
        try:
            data = json.loads(response.body)
        except ValueError:
            selectors = read_selectors(source, endpoint)
            if not selectors:
                continue
            one = htmlparse.matches(response.text('utf-8'), selectors)
            out[endpoint] = shapes.merge(out[endpoint], one) if endpoint in out else one
            continue
        one = data_shape(source, endpoint, trim_data(source, endpoint, data))
        out[endpoint] = shapes.merge(out[endpoint], one) if endpoint in out else one
    return out


def build_shape_index(directory: Path) -> dict[str, Any]:
    """Shape of every JSON or HTML file (status 200) of a fixture directory, by file.

    The shape of an HTML file is its matching selectors (`htmlparse.matches`).
    """
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    source = manifest['source']
    index = {}
    for entry in manifest.get('entries', []):
        file = entry.get('file')
        if not file or int(entry.get('status', 200)) != 200:
            continue
        body = (directory / file).read_bytes()
        endpoint = endpoint_of(entry['url'], source)
        try:
            data = json.loads(body)
        except ValueError:
            selectors = read_selectors(source, endpoint)
            if selectors:
                index[file] = htmlparse.matches(body.decode('utf-8'), selectors)
            continue
        index[file] = data_shape(source, endpoint, trim_data(source, endpoint, data))
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
    source = manifest.get('source')
    out: dict[str, Any] = {}
    for entry in manifest.get('entries', []):
        file = entry.get('file')
        if file not in index:
            continue
        endpoint = endpoint_of(entry['url'], source)
        one = index[file]
        out[endpoint] = shapes.merge(out[endpoint], one) if endpoint in out else one
    return out


# -- paths ('[].sommets[].latlon') ------------------------------------------


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


def _at(shape, path: str):
    """Return the node of a shape at a path (first list item), or None."""
    node = shape
    for step in _TOKEN.findall(path):
        if isinstance(node, list):
            node = node[0] if node else None
            if step == LIST_ITEMS:
                continue
        if not isinstance(node, dict) or step not in node:
            return None
        node = node[step]
    return node


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
    for endpoint, selectors in sorted(
        getattr(adapter, 'REQUIRED_SELECTORS', {}).items()
    ):
        for selector in selectors:
            label = f'{endpoint}: {selector}'
            if endpoint not in actual:
                report.unchecked.append(f'{label} (endpoint not requested)')
            elif selector in actual[endpoint]:
                continue
            elif selector in expected.get(endpoint, {}):
                report.problems.append(f'{label} no longer matches')
            else:
                report.unchecked.append(f'{label} (no match in the sample)')
    for endpoint, by_path in sorted(getattr(adapter, 'EMBEDDED_HTML', {}).items()):
        for path, selectors in sorted(by_path.items()):
            for selector in selectors:
                label = f'{endpoint}: {path} {selector}'
                if endpoint not in actual:
                    report.unchecked.append(f'{label} (endpoint not requested)')
                    continue
                found = _at(actual[endpoint], path)
                if isinstance(found, dict) and selector in found:
                    continue
                before = _at(expected.get(endpoint, {}), path)
                if isinstance(before, dict) and selector in before:
                    report.problems.append(f'{label} no longer matches')
                else:
                    report.unchecked.append(f'{label} (no match in the sample)')
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
