"""Licence: no partner free text in the committed fixtures and recordings."""

import json

import pytest

from c2corg_api.partners import contract
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
    assert checked


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_required_paths_are_never_free_text_keys(source):
    for paths in REGISTRY[source].REQUIRED_PATHS.values():
        for path in paths:
            assert FORBIDDEN_KEYS.isdisjoint(contract._TOKEN.findall(path)), path
