from types import SimpleNamespace

import pytest

from c2corg_api.scripts.es import fingerprint


@pytest.fixture
def package(tmp_path, monkeypatch):
    """A fake c2corg_api package with the files the fingerprint is made of."""
    root = tmp_path / 'c2corg_api'
    for name in (
        'search/mapping.py',
        'search/mappings/waypoint_mapping.py',
        'models/common/sortable_search_attributes.py',
        'scripts/es/fill_index.py',
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'# {name}\nVALUE = 1\n'.encode())
    monkeypatch.setattr(
        fingerprint, 'c2corg_api', SimpleNamespace(__file__=str(root / '__init__.py'))
    )
    return root


def test_fingerprint_is_stable(package):
    assert fingerprint.compute_fingerprint() == fingerprint.compute_fingerprint()
    assert len(fingerprint.compute_fingerprint()) == 64


def test_fingerprint_ignores_line_endings(package):
    before = fingerprint.compute_fingerprint()
    for path in package.rglob('*.py'):
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    assert fingerprint.compute_fingerprint() == before


@pytest.mark.parametrize(
    'name',
    [
        'search/mappings/waypoint_mapping.py',
        'models/common/sortable_search_attributes.py',
        'scripts/es/fill_index.py',
    ],
)
def test_fingerprint_changes_with_the_indexing_code(package, name):
    before = fingerprint.compute_fingerprint()
    (package / name).write_bytes(b'VALUE = 2\n')
    assert fingerprint.compute_fingerprint() != before


def test_fingerprint_ignores_other_files(package):
    before = fingerprint.compute_fingerprint()
    (package / 'views').mkdir()
    (package / 'views' / 'waypoint.py').write_bytes(b'VALUE = 2\n')
    assert fingerprint.compute_fingerprint() == before


@pytest.fixture
def check(package, monkeypatch):
    """Runs `es_index_fingerprint check` with the given stored fingerprint."""
    monkeypatch.setattr(fingerprint, 'setup_logging', lambda config_uri: None)
    monkeypatch.setattr(fingerprint, 'get_appsettings', lambda *a, **kw: {})
    monkeypatch.setattr(fingerprint, 'configure_es_from_config', lambda settings: None)
    monkeypatch.setitem(fingerprint.elasticsearch_config, 'client', object())

    def run(stored):
        monkeypatch.setattr(fingerprint, 'stored_fingerprint', lambda client: stored)
        try:
            fingerprint.main(['es_index_fingerprint', 'check', 'test.ini'])
        except SystemExit as exit_:
            return exit_.code
        return 0

    return run


def test_check_matching(check):
    assert check(fingerprint.compute_fingerprint()) == 0


def test_check_different(check):
    assert check('0' * 64) == 1


def test_check_without_fingerprint(check):
    assert check(None) == 2
