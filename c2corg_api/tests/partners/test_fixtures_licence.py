"""Licence: no partner free text in the committed fixtures and recordings."""

import json
import re

import pytest

from c2corg_api.partners import contract, htmlparse
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.tests.partners.test_cli import FIXTURES

# keys that carry texts, photos or tracks written by the users of a partner
FORBIDDEN_KEYS = {
    'content',
    'recit',
    'conditions',
    'obs',
    'access',
    'photos',
    'photo',
    'media',
    'tracks',
    'skimo_equip',
    'commentaire',
    'commentaires',
    'comment',
    'description',
    'text',
    'texte',
    'body',
    'legende',
    'cond',
    'participants',
    'gpx',
    'topos',
}


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _keys(item)


def _json_files():
    """Every JSON answer of every fixture directory, with its source and endpoint."""
    params = []
    for directory in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        manifest = json.loads((directory / 'manifest.json').read_text('utf-8'))
        source = manifest['source']
        endpoints = {
            e['file']: contract.endpoint_of(e['url'], source)
            for e in manifest['entries']
            if e.get('file')
        }
        for path in sorted(directory.glob('*.json')):
            if path.name == contract.SHAPE_FILE:
                continue  # type names only: test_shape_files_hold_type_names
            endpoint = endpoints.get(path.name, '')
            params.append(
                pytest.param(path, source, endpoint, id=f'{directory.name}/{path.name}')
            )
    return params


# a GPX link is the only thing a fixture may hold of the tracks of a report
_GPX_LINK = re.compile(r'https?://[^\s"<>]+\.gpx', re.I)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _harmless(key, value, source, endpoint, path):
    """Whether a free-text key holds nothing real.

    Placeholders only, a GPX link (tracks) or a trimmed page (embedded HTML).
    """
    if key == 'tracks':
        return value is None or (
            isinstance(value, list)
            and all(
                isinstance(t, dict)
                and set(t) <= {'guid'}
                and _GPX_LINK.fullmatch(str(t.get('guid', '')))
                for t in value
            )
        )
    embedded = contract.embedded_html(source, endpoint)
    if len(path) == 1 and key in embedded:
        return isinstance(value, str) and (
            htmlparse.trim(value, embedded[key]) == value
        )
    return all(
        not text.strip() or contract.REDACTED.fullmatch(text)
        for text in _strings(value)
    )


def _free_text(node, source, endpoint, path=()):
    """Yield the paths of the free-text keys that hold real text."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = (*path, key)
            if key in FORBIDDEN_KEYS and not _harmless(
                key, value, source, endpoint, here
            ):
                yield '.'.join(here)
            yield from _free_text(value, source, endpoint, here)
    elif isinstance(node, list):
        for item in node:
            yield from _free_text(item, source, endpoint, (*path, '[]'))


@pytest.mark.parametrize(('path', 'source', 'endpoint'), _json_files())
def test_fixtures_have_no_free_text(path, source, endpoint):
    """No partner text: a free-text key only holds `[text N chars]` placeholders.

    The adapters read and store some texts (`HarvestedOuting.texts`, never served),
    so their keys are in the recordings, redacted (`REDACT_PATHS`). The tracks of
    gulliver hold their GPX link only; the HTML fragment of its front page is
    trimmed to the selectors read.
    """
    data = json.loads(path.read_text(encoding='utf-8'))
    assert list(_free_text(data, source, endpoint)) == []


@pytest.mark.parametrize(
    'path', sorted(FIXTURES.glob(f'*/{contract.SHAPE_FILE}')), ids=str
)
def test_shape_files_hold_type_names(path):
    """A `shape.json` holds keys and type names, never a value of the site."""
    types = {'str', 'int', 'float', 'bool', 'null'}
    for text in _strings(json.loads(path.read_text(encoding='utf-8'))):
        assert (
            text in types
            or set(text.strip('"').split('|')) <= types
            or (
                text.startswith(('{', '['))  # an `any_of` alternative
            )
        ), text


@pytest.mark.parametrize(('path', 'source', 'endpoint'), _json_files())
def test_redacted_paths_only_hold_placeholders(path, source, endpoint):
    data = json.loads(path.read_text(encoding='utf-8'))
    for redacted in contract.redact_paths(source, endpoint):
        for value in _values(data, contract._TOKEN.findall(redacted)):
            for text in _strings(value):
                assert not text.strip() or contract.REDACTED.fullmatch(text), (
                    redacted,
                    text,
                )


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_recorded_fixtures_only_hold_the_paths_the_adapter_reads(source):
    """Trimming the committed fixtures changes nothing: nothing else is in them."""
    directory = FIXTURES / source
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    checked = 0
    for entry in manifest['entries']:
        if int(entry.get('status', 200)) != 200 or not entry['file'].endswith('.json'):
            continue
        data = json.loads((directory / entry['file']).read_text(encoding='utf-8'))
        endpoint = contract.endpoint_of(entry['url'], source)
        assert endpoint in REGISTRY[source].REQUIRED_PATHS, entry['file']
        assert contract.trim_data(source, endpoint, data) == data, entry['file']
        checked += 1
    assert checked or REGISTRY[source].REQUIRED_SELECTORS  # an HTML source


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_required_paths_are_never_free_text_keys(source):
    """A path through a free-text key is redacted, a GPX link or a trimmed page."""
    for endpoint, paths in REGISTRY[source].REQUIRED_PATHS.items():
        redacted = contract.redact_paths(source, endpoint)
        embedded = contract.embedded_html(source, endpoint)
        for path in paths:
            if path in redacted or path in embedded or path.endswith('tracks[].guid'):
                continue
            assert FORBIDDEN_KEYS.isdisjoint(contract._TOKEN.findall(path)), path


def _values(node, tokens):
    if not tokens:
        yield node
    elif tokens[0] == '[]':
        for item in node if isinstance(node, list) else []:
            yield from _values(item, tokens[1:])
    elif tokens[0] == contract.WILDCARD and isinstance(node, dict):
        for item in node.values():
            yield from _values(item, tokens[1:])
    elif isinstance(node, dict) and tokens[0] in node:
        yield from _values(node[tokens[0]], tokens[1:])


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_recorded_author_identities_are_pseudonymised(source):
    """A public repository: a recording holds "user1", "user2"... only."""
    directory = FIXTURES / source
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['synthetic']:
        pytest.skip('synthetic fixtures hold invented names')
    adapter = REGISTRY[source]
    checked = 0
    for entry in manifest['entries']:
        if not entry['file'].endswith('.json') or int(entry.get('status', 200)) != 200:
            continue
        data = json.loads((directory / entry['file']).read_text(encoding='utf-8'))
        endpoint = contract.endpoint_of(entry['url'], source)
        for path in getattr(adapter, 'PSEUDONYMISE_PATHS', {}).get(endpoint, ()):
            for value in _values(data, contract._TOKEN.findall(path)):
                assert re.fullmatch(r'user\d+', str(value)), (entry['file'], path)
                checked += 1
    assert checked or source != 'skitour'


def _html_fixtures():
    return [
        pytest.param(
            source, entry['file'], entry['url'], id=f'{source}/{entry["file"]}'
        )
        for source in sorted(REGISTRY)
        if getattr(REGISTRY[source], 'REQUIRED_SELECTORS', None)
        for entry in json.loads(
            (FIXTURES / source / 'manifest.json').read_text(encoding='utf-8')
        )['entries']
        if entry['file'].endswith(('.html', '.xml'))
        and int(entry.get('status', 200)) == 200
    ]


@pytest.mark.parametrize(('source', 'file', 'url'), _html_fixtures())
def test_html_fixtures_only_hold_the_selectors_the_adapter_reads(source, file, url):
    """Same allow-list for HTML: trimming changes nothing, no media, no other script."""
    text = (FIXTURES / source / file).read_text(encoding='utf-8')
    selectors = contract.read_selectors(source, contract.endpoint_of(url, source))
    assert selectors, file
    assert htmlparse.trim(text, selectors) == text
    soup = htmlparse.parse(text)
    assert not soup.find(['img', 'style', 'iframe', 'video', 'audio'])
    # a script only when the adapter reads it (the map markers of a page)
    read = {id(tag) for selector in selectors for tag in soup.select(selector)}
    scripts = soup.find_all('script')
    assert all(id(tag) in read for tag in scripts), file
    # texts are short fields (a title, a name, a number), never a narrative
    longest = max(
        (
            len(t.strip())
            for t in soup.find_all(string=True)
            if t.parent.name != 'script'
        ),
        default=0,
    )
    assert longest <= 200, file


_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}', re.I)


def _fixture_files():
    return [
        pytest.param(path, id=f'{directory.name}/{path.name}')
        for directory in sorted(p for p in FIXTURES.iterdir() if p.is_dir())
        for path in sorted(directory.iterdir())
        if path.suffix in ('.json', '.html', '.txt', '.xml', '.gpx')
    ]


@pytest.mark.parametrize('path', _fixture_files())
def test_fixtures_hold_no_email_address(path):
    """No e-mail of a partner user (on-ice.it keeps one in an HTML comment)."""
    text = path.read_text(encoding='utf-8', errors='replace')
    assert not _EMAIL.search(text), path.name


def test_there_is_an_html_fixture_to_check():
    assert any(p.values[0] == 'bivouak' for p in _html_fixtures())


@pytest.mark.parametrize(('source', 'file', 'url'), _html_fixtures())
def test_html_author_identities_are_pseudonymised(source, file, url):
    """The HTML counterpart of `PSEUDONYMISE_PATHS`: "user1", "user2"... only."""
    directory = FIXTURES / source
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['synthetic']:
        pytest.skip('synthetic fixtures hold invented names')
    endpoint = contract.endpoint_of(url, source)
    soup = htmlparse.parse((directory / file).read_text(encoding='utf-8'))
    for selector in contract.pseudonymise_selectors(source, endpoint):
        for tag in soup.select(selector):
            text = htmlparse.text_of(tag)
            assert not text or htmlparse.PSEUDONYM.fullmatch(text), (file, text)
            for attr in ('href', 'data-href'):
                if tag.get(attr):
                    last = tag[attr].rstrip('/').rsplit('/', 1)[-1]
                    assert re.fullmatch(r'user\d+(\.\w+)?', last), (file, tag[attr])


def test_html_sources_with_authors_pseudonymise_them():
    """An HTML adapter that reads an author link lists it to pseudonymise."""
    for source, adapter in REGISTRY.items():
        selectors = getattr(adapter, 'REQUIRED_SELECTORS', {})
        for endpoint, wanted in selectors.items():
            authors = [s for s in wanted if 'author' in s or 'autor' in s]
            pseudonymised = contract.pseudonymise_selectors(source, endpoint)
            assert set(authors) <= set(pseudonymised), (source, endpoint)
