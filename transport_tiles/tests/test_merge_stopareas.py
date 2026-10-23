import merge_stopareas


def osm_stop(lon, lat, name='Gare'):
    return {
        'type': 'Feature',
        'properties': {'name': name, 'lines': 'A', 'modes': 'bus'},
        'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
    }


def stoparea(navitia_id, lon, lat, name='Gare', line='A', operator='Sibra'):
    return {
        'navitia_id': navitia_id,
        'name': name,
        'line': line,
        'operator': operator,
        'lon': lon,
        'lat': lat,
    }


def test_osm_stop_near_a_stoparea_gets_its_navitia_id():
    stops = [osm_stop(6.0, 45.0)]
    # about 11 m to the east
    areas = [stoparea('stop_area:SIB:1', 6.00014, 45.0)]

    merged = list(merge_stopareas.merge(stops, areas))

    assert len(merged) == 1
    assert merged[0]['properties']['navitia_id'] == 'stop_area:SIB:1'
    assert 'source' not in merged[0]['properties']


def test_stoparea_without_osm_stop_is_added():
    stops = [osm_stop(6.0, 45.0)]
    # about 110 m away
    areas = [stoparea('stop_area:SIB:2', 6.0, 45.001, name='Mairie')]

    merged = list(merge_stopareas.merge(stops, areas))

    assert len(merged) == 2
    assert 'navitia_id' not in merged[0]['properties']
    added = merged[1]
    assert added['properties']['navitia_id'] == 'stop_area:SIB:2'
    assert added['properties']['source'] == 'navitia'
    assert added['properties']['name'] == 'Mairie'
    assert added['properties']['lines'] == 'A'
    assert added['properties']['operator'] == 'Sibra'
    assert added['properties']['tippecanoe'] == {'minzoom': 12}
    assert added['geometry']['coordinates'] == [6.0, 45.001]


def test_stoparea_matching_two_osm_stops_is_not_added_again():
    # the two directions of a street: one OSM stop on each side
    stops = [osm_stop(6.0, 45.0), osm_stop(6.0001, 45.0)]
    areas = [stoparea('stop_area:SIB:3', 6.00005, 45.0)]

    merged = list(merge_stopareas.merge(stops, areas))

    assert len(merged) == 2
    assert {s['properties']['navitia_id'] for s in merged} == {'stop_area:SIB:3'}


def test_nearest_stoparea_is_chosen():
    stops = [osm_stop(6.0, 45.0)]
    areas = [
        stoparea('far', 6.0002, 45.0),
        stoparea('near', 6.00005, 45.0),
    ]

    merged = list(merge_stopareas.merge(stops, areas))

    # both stop areas are within 30 m: the nearest one is attached, none is added
    assert merged[0]['properties']['navitia_id'] == 'near'
    assert len(merged) == 1


def test_without_stopareas_the_stops_are_unchanged():
    stops = [osm_stop(6.0, 45.0)]

    merged = list(merge_stopareas.merge(stops, []))

    assert merged == [osm_stop(6.0, 45.0)]
