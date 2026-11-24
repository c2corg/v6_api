"""The maintainer CLI, offline: a fake transport stands for the partner site."""

import datetime
import json
import shutil

import pytest

from c2corg_api.partners import __main__ as cli
from c2corg_api.partners import contract
from c2corg_api.partners.adapter import SourceBlocked
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import FixtureTransport

FIXTURES = cli.DEFAULT_FIXTURES


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A copy of the fixtures served as if it were the live site.

    Returns the directory; edit its files before running the CLI.
    """
    root = tmp_path / 'site'
    shutil.copytree(FIXTURES, root)
    monkeypatch.setenv('SKITOUR_API_KEY', 'test-key')
    monkeypatch.setattr(
        cli,
        'make_transport',
        lambda adapter: FixtureTransport(root, adapter.name, rate=adapter.rate),
    )
    return root


def _edit(path, change):
    data = json.loads(path.read_text(encoding='utf-8'))
    change(data)
    path.write_text(json.dumps(data), encoding='utf-8')


def _today():
    return datetime.datetime.now(datetime.UTC).date().isoformat()


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_committed_shape_json_covers_required_paths(source):
    adapter = REGISTRY[source]()
    expected = contract.fixture_shapes(FIXTURES / source)
    assert set(adapter.REQUIRED_PATHS) <= set(expected)
    for endpoint, paths in adapter.REQUIRED_PATHS.items():
        for path in paths:
            assert contract.lookup(expected[endpoint], path)[0] == 'ok', path


def test_shape_json_is_up_to_date():
    """Fixtures edited without regenerating shape.json would fool `shapes`."""
    for source in REGISTRY:
        directory = FIXTURES / source
        committed = json.loads((directory / 'shape.json').read_text(encoding='utf-8'))
        assert committed == contract.build_shape_index(directory)


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_shapes_offline_matches_fixtures(source, capsys, monkeypatch):
    monkeypatch.delenv('SKITOUR_API_KEY', raising=False)
    assert cli.main(['shapes', source, '--offline']) == 0
    assert 'OK: every field' in capsys.readouterr().out


def test_shapes_live_no_diff(site, capsys):
    assert cli.main(['shapes', 'skitour']) == 0
    out = capsys.readouterr().out
    assert 'sorties: no change' in out and 'OK' in out


def test_shapes_reports_added_key_without_failing(site, capsys):
    def add(data):
        data[0]['nouveau'] = 1

    _edit(site / 'skitour/sorties_c1_l200_p1.json', add)
    assert cli.main(['shapes', 'skitour']) == 0
    assert '+ [].nouveau: int' in capsys.readouterr().out


def test_shapes_removed_key_is_breaking(site, capsys):
    def remove(data):
        for outing in data:
            for summit in outing.get('sommets') or []:
                summit.pop('latlon', None)

    for page in ('p1', 'p2'):
        _edit(site / f'skitour/sorties_c1_l200_{page}.json', remove)
    assert cli.main(['shapes', 'skitour']) == 1
    out = capsys.readouterr().out
    assert 'BREAKING' in out
    assert 'sorties: [].sommets[].latlon is missing' in out
    assert '- [].sommets[].latlon' in out


def test_shapes_retyped_key_is_breaking(site, capsys):
    def retype(data):
        for outing in data:
            outing['id'] = str(outing['id'])

    for page in ('p1', 'p2'):
        _edit(site / f'skitour/sorties_c1_l200_{page}.json', retype)
    assert cli.main(['shapes', 'skitour']) == 1
    assert 'sorties: [].id changed type: int -> str' in capsys.readouterr().out


def test_shapes_gulliver_nested_path_removed(site, capsys):
    def remove(data):
        for route in data if isinstance(data, list) else [data]:
            route['meta']['geo'].pop('coords')

    for path in site.glob('gulliver/routes_id*.json'):
        if path.name != 'routes_id61022.json':
            _edit(path, remove)
    assert cli.main(['shapes', 'gulliver']) == 1
    assert 'routes: meta.geo.coords.lat is missing' in capsys.readouterr().out


def test_shapes_unparsable_answer_exits_1(site, capsys):
    for page in ('p1', 'p2'):
        _edit(
            site / f'skitour/sorties_c1_l200_{page}.json',
            lambda data: data.clear(),
        )
    (site / 'skitour/sorties_c1_l200_p1.json').write_text('{}', encoding='utf-8')
    assert cli.main(['shapes', 'skitour']) == 1
    assert 'cannot parse' in capsys.readouterr().err


class BlockedTransport:
    request_count = 0

    def get(self, url, *, params=None, headers=None):
        raise SourceBlocked(f'challenge page from {url} (HTTP 403)')


@pytest.mark.parametrize('command', ['shapes', 'record'])
def test_blocked_site_exits_2(command, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, 'make_transport', lambda adapter: BlockedTransport())
    argv = [command, 'gulliver']
    if command == 'record':
        argv += ['--out', str(tmp_path / 'out')]
    assert cli.main(argv) == 2
    assert 'blocked by the site' in capsys.readouterr().err


def test_down_site_exits_2(monkeypatch, capsys):
    """skitour_down holds the 503 page the sandbox gets from skitour.fr."""
    monkeypatch.setenv('SKITOUR_API_KEY', 'test-key')
    monkeypatch.setattr(
        cli,
        'make_transport',
        lambda adapter: FixtureTransport(FIXTURES, 'skitour_down'),
    )
    assert cli.main(['shapes', 'skitour']) == 2
    assert 'unreachable or down' in capsys.readouterr().err


def test_missing_key_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv('SKITOUR_API_KEY', raising=False)

    class NoRequest:
        request_count = 0

        def get(self, *args, **kwargs):
            pytest.fail('no request without a key')

    monkeypatch.setattr(cli, 'make_transport', lambda adapter: NoRequest())
    assert cli.main(['shapes', 'skitour']) == 2
    assert 'SKITOUR_API_KEY not set' in capsys.readouterr().err
    assert cli.main(['record', 'skitour', '--out', str(tmp_path)]) == 2


def test_shapes_without_shape_json_exits_2(capsys, tmp_path):
    shutil.copytree(FIXTURES / 'gulliver', tmp_path / 'gulliver')
    (tmp_path / 'gulliver/shape.json').unlink()
    assert (
        cli.main(['shapes', 'gulliver', '--offline', '--fixtures', str(tmp_path)]) == 2
    )
    assert 'no shape.json' in capsys.readouterr().err


def test_unknown_source_is_refused():
    with pytest.raises(SystemExit) as e:
        cli.main(['shapes', 'nope'])
    assert e.value.code == 2


def test_record_writes_fixtures(site, tmp_path, capsys):
    out = tmp_path / 'recorded'
    assert (
        cli.main(['record', 'skitour', '--out', str(out), '--since', '2026-11-20']) == 0
    )
    directory = out / 'skitour'
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['source'] == 'skitour'
    assert manifest['synthetic'] is False
    assert manifest['recorded_at'] == _today()
    # page 1 holds fewer than 200 outings: the adapter stops there
    (entry,) = manifest['entries']
    name = entry['file']
    assert name == 'sorties_c1_l200_p1.json'
    # the number of days back is not recorded: the fixture fits any `since`
    assert entry['params'] == {'c': '1', 'l': '200', 'p': '1'}
    assert 'api/sorties' in entry['url']
    # the key goes in a header, never into the files
    assert 'test-key' not in ''.join(p.read_text() for p in directory.iterdir())
    # the licensed texts of skitour are not kept
    recorded = (directory / name).read_text(encoding='utf-8')
    assert 'LICENSED' not in recorded
    assert json.loads(recorded)[0]['titre'] == 'Pointe de la Sana, face NE'
    shape = json.loads((directory / 'shape.json').read_text(encoding='utf-8'))
    assert sorted(shape) == [e['file'] for e in manifest['entries']]
    assert 'recorded 1 responses' in capsys.readouterr().out
    # leaves nothing behind but the source directory
    assert [p.name for p in out.iterdir()] == ['skitour']
    # and the recording can be replayed and checked against its own shapes
    assert cli.main(['shapes', 'skitour', '--offline', '--fixtures', str(out)]) == 0


def test_record_trims_payloads(site, tmp_path):
    def bulk(data):
        data['media'] = [{'url': 'x'}]
        data['meta']['things'] = list(range(100))

    _edit(site / 'gulliver/routes_id57949.json', bulk)

    def many(data):
        data[:] = [dict(data[0], ID=i) for i in range(1000, 1050)]

    _edit(site / 'gulliver/commentglobal_page1.json', many)
    out = tmp_path / 'recorded'
    assert cli.main(['record', 'gulliver', '--out', str(out)]) == 0
    route = json.loads((out / 'gulliver/routes_id57949.json').read_text())
    assert 'media' not in route
    assert len(route['meta']['things']) == contract.MAX_ITEMS
    comments = json.loads((out / 'gulliver/commentglobal_page1.json').read_text())
    assert len(comments) == contract.MAX_ITEMS
    assert 'content' not in comments[0]


def test_record_replaces_previous_recording_but_keeps_hand_made_files(site, tmp_path):
    out = tmp_path / 'recorded'
    (out / 'skitour').mkdir(parents=True)
    (out / 'skitour/manifest.json').write_text(
        json.dumps({'entries': [{'file': 'old.json'}]}), encoding='utf-8'
    )
    (out / 'skitour/old.json').write_text('[]', encoding='utf-8')
    (out / 'skitour/note.html').write_text('hand made', encoding='utf-8')
    assert cli.main(['record', 'skitour', '--out', str(out)]) == 0
    names = {p.name for p in (out / 'skitour').iterdir()}
    assert 'old.json' not in names and 'note.html' in names
    assert {'manifest.json', 'shape.json'} <= names


def test_failed_record_leaves_existing_fixtures_alone(monkeypatch, tmp_path, capsys):
    out = tmp_path / 'fixtures'
    shutil.copytree(FIXTURES / 'gulliver', out / 'gulliver')
    before = {p.name: p.read_bytes() for p in (out / 'gulliver').iterdir()}
    monkeypatch.setattr(cli, 'make_transport', lambda adapter: BlockedTransport())
    assert cli.main(['record', 'gulliver', '--out', str(out)]) == 2
    assert {p.name: p.read_bytes() for p in (out / 'gulliver').iterdir()} == before
    assert [p.name for p in out.iterdir()] == ['gulliver']


def test_since_must_be_a_date(capsys):
    with pytest.raises(SystemExit):
        cli.main(['record', 'skitour', '--since', 'yesterday'])
    assert 'YYYY-MM-DD' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('path', 'status'),
    [
        ('[].a', 'ok'),
        ('[].b[].c', 'ok'),
        ('[].b[].d', 'missing'),
        ('[].e[].f', 'unchecked'),
        ('[].g.h', 'ok'),
        ('a', 'ok'),  # a top list is entered implicitly
        ('zzz', 'missing'),
    ],
)
def test_lookup(path, status):
    shape = [
        {
            'a': 'int',
            'b': [{'c': 'str'}],
            'e': [],
            'g': {'any_of': ['"null"', '{"h": "str"}']},
        }
    ]
    assert contract.lookup(shape, path)[0] == status


def test_compatible_types():
    assert contract._compatible({'int'}, {'float'})
    assert contract._compatible({'str'}, {'null'})
    assert contract._compatible({'str', 'null'}, {'str'})
    assert not contract._compatible({'str'}, {'list'})
