import json

import reconcile


def line(fid, rels, coordinates, **properties):
    return {
        'type': 'Feature',
        'properties': {
            'fid': fid,
            'rels': ','.join(str(r) for r in rels),
            'mode': 'train',
            'tippecanoe': {'minzoom': 6},
            **properties,
        },
        'geometry': {'type': 'LineString', 'coordinates': coordinates},
    }


def stop(name, lon, lat, lines, modes='bus'):
    return {
        'type': 'Feature',
        'properties': {'name': name, 'lines': lines, 'modes': modes},
        'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
    }


def reconciled(tmp_path, features, function):
    source = tmp_path / 'in.geojsonl'
    target = tmp_path / 'out.geojsonl'
    reconcile.write(str(source), features)
    merged = function(str(source), str(target))
    return list(reconcile.read(str(target))), merged


def test_the_two_pieces_of_a_line_cut_at_the_border_become_one(tmp_path):
    west = line(
        100, [100], [[5.9, 46.2], [6.0, 46.2]], ref='TGV', name='Paris - Geneve'
    )
    east = line(100, [100, 101], [[6.0, 46.2], [6.1, 46.2]], ref='TGV')

    features, merged = reconciled(tmp_path, [west, east], reconcile.reconcile_lines)

    assert merged == 1
    assert len(features) == 1
    assert features[0]['geometry'] == {
        'type': 'LineString',
        'coordinates': [[5.9, 46.2], [6.0, 46.2], [6.1, 46.2]],
    }
    properties = features[0]['properties']
    assert properties['rels'] == '100,101'
    # what only one of the pieces knew is kept
    assert properties['name'] == 'Paris - Geneve'
    assert properties['ref'] == 'TGV'
    assert properties['tippecanoe'] == {'minzoom': 6}


def test_lines_that_share_nothing_are_left_alone(tmp_path):
    first = line(1, [1], [[5.0, 45.0], [5.1, 45.0]])
    second = line(2, [2], [[6.0, 45.0], [6.1, 45.0]])

    features, merged = reconciled(tmp_path, [first, second], reconcile.reconcile_lines)

    assert merged == 0
    assert features == [first, second]


def test_pieces_linked_one_to_the_next_are_all_joined(tmp_path):
    pieces = [
        line(10, [10], [[5.0, 45.0], [5.1, 45.0]]),
        line(30, [30, 20], [[5.2, 45.0], [5.3, 45.0]]),
        line(20, [10, 20], [[5.1, 45.0], [5.2, 45.0]]),
    ]

    features, merged = reconciled(tmp_path, pieces, reconcile.reconcile_lines)

    assert merged == 1
    assert len(features) == 1
    assert features[0]['properties']['rels'] == '10,20,30'
    assert features[0]['properties']['fid'] == 10
    assert len(features[0]['geometry']['coordinates']) == 4


def test_a_stop_found_in_two_extracts_is_one_stop(tmp_path):
    border = stop('Frontiere', 6.0, 46.2, 'A', 'bus')
    again = stop('Frontiere', 6.0, 46.2, 'B,A', 'tram')
    other = stop('Ailleurs', 6.5, 46.5, 'C')

    features, merged = reconciled(
        tmp_path, [border, other, again], reconcile.reconcile_stops
    )

    assert merged == 1
    by_name = {f['properties']['name']: f for f in features}
    assert len(features) == 2
    assert by_name['Frontiere']['properties']['lines'] == 'A,B'
    assert by_name['Frontiere']['properties']['modes'] == 'bus,tram'
    assert by_name['Ailleurs'] == other


def test_stops_of_the_same_name_at_different_places_stay_two(tmp_path):
    near = stop('Mairie', 6.0, 46.2, 'A')
    far = stop('Mairie', 6.01, 46.2, 'A')

    features, merged = reconciled(tmp_path, [near, far], reconcile.reconcile_stops)

    assert merged == 0
    assert len(features) == 2


def test_files_are_replaced(tmp_path):
    lines = tmp_path / 'lines.geojsonl'
    stops = tmp_path / 'stops.geojsonl'
    reconcile.write(
        str(lines),
        [
            line(1, [1], [[5.0, 45.0], [5.1, 45.0]]),
            line(1, [1], [[5.1, 45.0], [5.2, 45.0]]),
        ],
    )
    reconcile.write(str(stops), [stop('A', 5.0, 45.0, 'X'), stop('A', 5.0, 45.0, 'Y')])

    reconcile.main(str(lines), str(stops))

    assert len(lines.read_text().splitlines()) == 1
    assert json.loads(stops.read_text())['properties']['lines'] == 'X,Y'
    assert not (tmp_path / 'lines.geojsonl.reconciled').exists()
