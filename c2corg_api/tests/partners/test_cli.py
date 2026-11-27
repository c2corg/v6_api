"""The maintainer CLI, offline: a fake transport stands for the partner site."""

import datetime
import json
import shutil

import pytest

from c2corg_api.partners import __main__ as cli
from c2corg_api.partners import contract
from c2corg_api.partners.adapter import SourceBlocked
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

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


def test_shapes_ignores_fields_the_adapter_does_not_read(site, capsys):
    """Added fields are dropped like in a recording: no diff, no failure."""

    def add(data):
        data[0]['nouveau'] = 1

    _edit(site / 'skitour/sorties_c1_l200_p1.json', add)
    assert cli.main(['shapes', 'skitour']) == 0
    out = capsys.readouterr().out
    assert 'nouveau' not in out
    assert 'sorties: no change' in out


def test_shapes_removed_key_is_breaking(site, capsys):
    def remove(data):
        for outing in data:
            for summit in outing.get('sommets') or []:
                summit.pop('lat', None)

    for page in ('p1',):
        _edit(site / f'skitour/sorties_c1_l200_{page}.json', remove)
    assert cli.main(['shapes', 'skitour']) == 1
    out = capsys.readouterr().out
    assert 'BREAKING' in out
    assert 'sorties: [].sommets[].lat is missing' in out
    assert '- [].sommets[].lat' in out


def test_shapes_retyped_key_is_breaking(site, capsys):
    def retype(data):
        for outing in data:
            outing['id'] = int(outing['id'])

    for page in ('p1',):
        _edit(site / f'skitour/sorties_c1_l200_{page}.json', retype)
    assert cli.main(['shapes', 'skitour']) == 1
    assert 'sorties: [].id changed type: str -> int' in capsys.readouterr().out


def test_shapes_gulliver_nested_path_removed(site, capsys):
    def remove(data):
        for route in data.values():
            route['meta']['geo'].pop('coords', None)

    for path in site.glob('gulliver/routes_id*.json'):
        _edit(path, remove)
    assert cli.main(['shapes', 'gulliver']) == 1
    assert 'routes: *.meta.geo.coords.value.lat is missing' in capsys.readouterr().out


def test_shapes_gulliver_front_page_selector_gone(site, capsys):
    """The links of the HTML fragment in the JSON of the front page are checked."""

    def rename(data):
        data['content'] = data['content'].replace('btn-ghost', 'btn-other')

    _edit(site / 'gulliver/comments_sortingid.json', rename)
    assert cli.main(['shapes', 'gulliver']) == 1
    out = capsys.readouterr().out
    assert 'front_page_comments: content a.btn-ghost' in out
    assert 'no longer matches' in out


def test_shapes_unparsable_answer_exits_1(site, capsys):
    for page in ('p1',):
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


def test_rejected_key_exits_2_as_blocked(monkeypatch, capsys):
    """skitour answers HTTP 200 + {"ERROR": ...}: blocked, not a shape diff."""
    monkeypatch.setenv('SKITOUR_API_KEY', 'test-key')
    monkeypatch.setattr(
        cli,
        'make_transport',
        lambda adapter: FixtureTransport(FIXTURES, 'skitour_bad_key'),
    )
    assert cli.main(['shapes', 'skitour']) == 2
    assert 'blocked by the site: skitour API error: INVALID API KEY' in (
        capsys.readouterr().err
    )


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
    assert (
        json.loads(recorded)[0]['titre']
        == 'Dôme des Rousses, croupe nord et lac du milieu'
    )
    shape = json.loads((directory / 'shape.json').read_text(encoding='utf-8'))
    assert sorted(shape) == [e['file'] for e in manifest['entries']]
    assert 'recorded 1 responses' in capsys.readouterr().out
    # leaves nothing behind but the source directory
    assert [p.name for p in out.iterdir()] == ['skitour']
    # and the recording can be replayed and checked against its own shapes
    assert cli.main(['shapes', 'skitour', '--offline', '--fixtures', str(out)]) == 0


def test_record_trims_payloads(site, tmp_path):
    def many(data):
        first = next(iter(data.values()))
        data.clear()
        data.update({str(i): dict(first, ID=str(i)) for i in range(1000, 1050)})

    _edit(site / 'gulliver/commentglobal_page1.json', many)
    out = tmp_path / 'recorded'
    assert cli.main(['record', 'gulliver', '--out', str(out)]) == 0
    comments = json.loads((out / 'gulliver/commentglobal_page1.json').read_text())
    assert len(comments) == contract.MAX_ITEMS


def test_record_drops_and_redacts_gulliver_free_text(site, tmp_path):
    """Licence: what the adapter does not read is dropped, its texts redacted."""

    def add_text(data):
        for comment in data.values():
            comment['content'] = '<p>COMMENT-TEXT</p>'
            comment['tracks'] = [
                {
                    'guid': 'https://www.gulliver.it/wp-content/uploads/a.gpx',
                    'gpx': 'TRACK-DATA',
                    'user_nicename': 'TRACK-AUTHOR',
                }
            ]
            comment['new_field'] = 'NEW-FREE-TEXT'
            comment['meta'] = {
                'access': {'label': 'Accesso', 'value': 'ACCESS-TEXT'},
                'obs': {'label': 'Osservazioni', 'value': 'OBS-TEXT'},
                'skimo_equip': {'label': 'Equip', 'value': 'EQUIP-TEXT'},
                'snow_top': {'label': 'Neve', 'value': 'SNOW-TEXT'},
                'snow_alt': {'label': 'Quota', 'value': '1500'},
            }

    def add_route_text(data):
        for route in data.values():
            route['media'] = [{'url': 'MEDIA'}]
            route['content'] = 'ROUTE-DESCRIPTION'
            route['meta']['data']['note'] = {'value': 'ROUTE-NOTE'}
            route['meta']['geo']['coords']['value']['address'] = 'ROUTE-ADDRESS'

    _edit(site / 'gulliver/commentglobal_page1.json', add_text)
    for path in site.glob('gulliver/routes_id*.json'):
        _edit(path, add_route_text)
    out = tmp_path / 'recorded'
    assert cli.main(['record', 'gulliver', '--out', str(out)]) == 0
    recorded = ''.join(p.read_text() for p in (out / 'gulliver').iterdir())
    for text in (
        'COMMENT-TEXT',
        'TRACK-DATA',
        'TRACK-AUTHOR',
        'NEW-FREE-TEXT',
        'ACCESS-TEXT',
        'OBS-TEXT',
        'EQUIP-TEXT',
        'SNOW-TEXT',
        'Accesso',
        'MEDIA',
        'ROUTE-DESCRIPTION',
        'ROUTE-NOTE',
        'ROUTE-ADDRESS',
    ):
        assert text not in recorded
    # what the adapter reads is kept, its texts as placeholders
    page = json.loads((out / 'gulliver/commentglobal_page1.json').read_text())
    comment = next(iter(page.values()))
    assert set(comment) == {
        'ID',
        'comment_date',
        'comment_post_ID',
        'permalink',
        'term',
        'user_nicename',
        'content',
        'tracks',
        'meta',
    }
    assert comment['content'] == '[text 19 chars]'
    assert comment['meta']['access'] == {'value': '[text 11 chars]'}
    assert comment['meta']['snow_alt'] == {'value': '1500'}
    assert comment['tracks'] == [
        {'guid': 'https://www.gulliver.it/wp-content/uploads/a.gpx'}
    ]
    assert comment['user_nicename'].startswith('user')
    route = json.loads((out / 'gulliver/routes_id88735.json').read_text())['88735']
    assert route['meta']['data']['grade_skimo'] == {'value': 'MS'}
    assert set(route['meta']['geo']['coords']['value']) == {'lat', 'lng'}
    assert route['district'] == 'Hautes-Alpes'
    # the HTML fragment of the front page keeps the report links only
    front = json.loads((out / 'gulliver/comments_sortingid.json').read_text())
    assert set(front) == {'content'}
    assert 'combo-review' in front['content']


def test_record_drops_skitour_free_text(site, tmp_path):
    def add_text(data):
        for item in data:
            item['commentaires'] = 'COMMENTS-TEXT'
            item['meteo'] = 'WEATHER-TEXT'
            item['recit'] = 'RECIT-TEXT'
            item['cond'] = 'COND-TEXT'
            item['photos'] = [{'id': 'PHOTO-ID'}]
            item['participants'] = [{'pseudo': 'PARTICIPANT-NAME'}]
            for summit in item.get('sommets') or []:
                summit['description'] = 'SUMMIT-TEXT'

    _edit(site / 'skitour/sorties_c1_l200_p1.json', add_text)
    out = tmp_path / 'recorded'
    assert cli.main(['record', 'skitour', '--out', str(out)]) == 0
    recorded = (out / 'skitour/sorties_c1_l200_p1.json').read_text()
    for text in (
        'COMMENTS-TEXT',
        'WEATHER-TEXT',
        'SUMMIT-TEXT',
        'RECIT-TEXT',
        'COND-TEXT',
        'PHOTO-ID',
        'PARTICIPANT-NAME',
    ):
        assert text not in recorded
    first = json.loads(recorded)[0]
    assert first['sommets'][0]['lat'] and first['dif_ski'] == '2.1'


def test_trim_keeps_nothing_of_an_unknown_endpoint():
    assert contract.trim_data('skitour', 'other', [{'a': 1}]) == []
    assert contract.trim_data('nope', 'sorties', {'a': 1}) == {}


def test_shapes_use_the_same_paths_as_the_recorder():
    """The shapes of a live answer are compared after the same trimming."""
    live = [{'id': 1, 'titre': 't', 'recit': 'TEXT', 'conditions': 'TEXT'}]
    shape = contract.captured_shapes(
        'skitour',
        [
            HttpResponse(
                200, {}, json.dumps(live).encode(), 'https://skitour.fr/api/sorties'
            )
        ],
    )
    assert shape['sorties'] == [{'id': 'int', 'titre': 'str'}]


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


def test_secrets_from_env_or_key_file(monkeypatch, tmp_path):
    adapter = REGISTRY['skitour']()
    monkeypatch.delenv('SKITOUR_API_KEY', raising=False)
    monkeypatch.delenv('SKITOUR_API_KEY_FILE', raising=False)
    assert cli.secrets_from_env(adapter) == {}
    key_file = tmp_path / 'key'
    key_file.write_text('file-key\n', encoding='utf-8')
    monkeypatch.setenv('SKITOUR_API_KEY_FILE', str(key_file))
    assert cli.secrets_from_env(adapter) == {'SKITOUR_API_KEY': 'file-key'}
    # the variable wins over the file
    monkeypatch.setenv('SKITOUR_API_KEY', 'env-key')
    assert cli.secrets_from_env(adapter) == {'SKITOUR_API_KEY': 'env-key'}
    # an unreadable file is no secret
    monkeypatch.delenv('SKITOUR_API_KEY')
    monkeypatch.setenv('SKITOUR_API_KEY_FILE', str(tmp_path / 'missing'))
    assert cli.secrets_from_env(adapter) == {}


def test_record_pseudonymises_authors_consistently(site, tmp_path):
    def authors(data):
        for i, item in enumerate(data):
            item['auteur'] = {'id': str(i), 'pseudo': 'Alice' if i % 2 else 'Bob'}

    _edit(site / 'skitour/sorties_c1_l200_p1.json', authors)
    out = tmp_path / 'recorded'
    assert cli.main(['record', 'skitour', '--out', str(out)]) == 0
    recorded = json.loads((out / 'skitour/sorties_c1_l200_p1.json').read_text())
    pseudos = [item['auteur']['pseudo'] for item in recorded]
    assert pseudos[:3] == ['user1', 'user2', 'user1']
    assert 'Alice' not in json.dumps(recorded) and 'Bob' not in json.dumps(recorded)


def test_pseudonymise_keeps_the_type_of_ids():
    names = {}
    data = [{'a': {'id': 77, 'n': 'x'}}, {'a': {'id': 77, 'n': 'y'}}]
    out = contract._replace(data, contract._tree(['[].a.id']), names)
    assert out[0]['a']['id'] == out[1]['a']['id']
    assert isinstance(out[0]['a']['id'], int)
    assert out[0]['a']['n'] == 'x'
