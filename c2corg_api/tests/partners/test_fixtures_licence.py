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
    return [
        pytest.param(path, id=f'{directory.name}/{path.name}')
        for directory in sorted(p for p in FIXTURES.iterdir() if p.is_dir())
        for path in sorted(directory.glob('*.json'))
    ]


@pytest.mark.parametrize('path', _json_files())
def test_fixtures_have_no_free_text(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    assert FORBIDDEN_KEYS.isdisjoint(_keys(data))


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
        endpoint = contract.endpoint_of(entry['url'])
        assert endpoint in REGISTRY[source].REQUIRED_PATHS, entry['file']
        assert contract.trim_data(source, endpoint, data) == data, entry['file']
        checked += 1
    assert checked or REGISTRY[source].REQUIRED_SELECTORS  # an HTML source


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_required_paths_are_never_free_text_keys(source):
    for paths in REGISTRY[source].REQUIRED_PATHS.values():
        for path in paths:
            assert FORBIDDEN_KEYS.isdisjoint(contract._TOKEN.findall(path)), path


def _values(node, tokens):
    if not tokens:
        yield node
    elif tokens[0] == '[]':
        for item in node if isinstance(node, list) else []:
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
        endpoint = contract.endpoint_of(entry['url'])
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
        if entry['file'].endswith('.html') and int(entry.get('status', 200)) == 200
    ]


@pytest.mark.parametrize(('source', 'file', 'url'), _html_fixtures())
def test_html_fixtures_only_hold_the_selectors_the_adapter_reads(source, file, url):
    """Same allow-list for HTML: trimming changes nothing, no media, no other script."""
    text = (FIXTURES / source / file).read_text(encoding='utf-8')
    selectors = contract.read_selectors(source, contract.endpoint_of(url))
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


def test_there_is_an_html_fixture_to_check():
    assert any(p.values[0] == 'bivouak' for p in _html_fixtures())


@pytest.mark.parametrize(('source', 'file', 'url'), _html_fixtures())
def test_html_author_identities_are_pseudonymised(source, file, url):
    """The HTML counterpart of `PSEUDONYMISE_PATHS`: "user1", "user2"... only."""
    directory = FIXTURES / source
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['synthetic']:
        pytest.skip('synthetic fixtures hold invented names')
    endpoint = contract.endpoint_of(url)
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
