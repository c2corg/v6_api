import datetime
import os

import build_lines

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixture.osm')
TODAY = datetime.date(2026, 10, 23)


def build():
    return build_lines.build(FIXTURE, today=TODAY)


def line(lines, ref=None, name=None):
    found = [
        line
        for line in lines
        if line['properties'].get('ref') == ref
        and line['properties'].get('name') == name
    ]
    assert len(found) == 1
    return found[0]


def test_directions_are_merged_in_one_line():
    lines, _ = build()

    properties = line(lines, ref='A')['properties']
    assert properties['mode'] == 'bus'
    assert properties['network'] == 'Sibra'
    assert properties['colour'] == '#ff0000'
    assert properties['fid'] == 100
    assert properties['rels'] == '100,101'
    assert properties['tippecanoe'] == {'minzoom': 10}
    geometry = line(lines, ref='A')['geometry']
    assert geometry['type'] == 'LineString'
    assert len(geometry['coordinates']) == 4


def test_closed_and_not_yet_open_lines_are_left_out():
    lines, _ = build()

    refs = {line['properties'].get('ref') for line in lines}
    # Z is disused, Y ended in 2020, V only starts in 2999, hiking is no transport
    assert refs == {'A', 'W', None}


def test_abandoned_ways_are_not_drawn():
    lines, _ = build()

    # route 107 is made of a working way and an abandoned railway
    geometry = line(lines, name='TER Annecy')['geometry']
    assert [tuple(c) for c in geometry['coordinates']] == [(7.0, 46.0), (7.01, 46.0)]


def test_how_often_a_line_runs_is_kept_when_tagged():
    lines, _ = build()

    properties = line(lines, ref='W')['properties']
    assert properties['seasonal'] == 'winter'
    assert properties['opening_hours'] == 'Dec-Apr'
    assert properties['website'] == 'https://example.org/w'
    assert 'seasonal' not in line(lines, ref='A')['properties']


def test_train_line_without_ref_keeps_its_name():
    lines, _ = build()

    train = line(lines, name='TER Lyon - Geneve')['properties']
    assert train['mode'] == 'train'
    assert 'ref' not in train


def test_stops_prefer_platforms_and_list_their_lines():
    _, stops = build()

    names = sorted(stop['properties']['name'] for stop in stops)
    # route 100 has two stop positions (Mairie, Gare), route 101 one platform (Mairie)
    assert names == ['Gare', 'Mairie', 'Mairie']
    assert all(stop['properties']['lines'] == 'A' for stop in stops)
    assert all(stop['properties']['modes'] == 'bus' for stop in stops)


def test_node_ids_read_in_several_windows_give_the_same_result(monkeypatch):
    expected = build()

    monkeypatch.setattr(build_lines, 'NODE_ID_WINDOW', 3)

    assert build() == expected


def test_partial_dates():
    assert build_lines.date_bounds('2019') == (
        datetime.date(2019, 1, 1),
        datetime.date(2019, 12, 31),
    )
    assert build_lines.date_bounds('2020-02') == (
        datetime.date(2020, 2, 1),
        datetime.date(2020, 2, 29),
    )
    assert build_lines.date_bounds('2020-02-10') == (
        datetime.date(2020, 2, 10),
        datetime.date(2020, 2, 10),
    )
    assert build_lines.date_bounds('~1990') is None
    assert build_lines.date_bounds('2019-13') is None
    assert build_lines.date_bounds(None) is None
