import json
from datetime import date
from unittest.mock import patch

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.search.search_filters import build_query
from c2corg_api.tests.search import reset_search_index
from c2corg_api.views.document_map import (
    _geohash_center,
    _heatmap_precision,
    _lon_lat_to_3857,
    tracks_limit,
    tracks_overlay_enabled,
)

BBOX = '635000,5723000,637000,5724000'


def _outing(title, activities, day, geom, geom_detail=None, **fields):
    return Outing(
        activities=activities,
        date_start=date(2016, 1, day),
        date_end=date(2016, 1, day),
        locales=[OutingLocale(lang='en', title=title)],
        geometry=DocumentGeometry(geom=geom, geom_detail=geom_detail),
        **fields,
    )


def _route(title, activities, geom, geom_detail=None, title_prefix=None, **fields):
    return Route(
        activities=activities,
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
        locales=[RouteLocale(lang='en', title=title, title_prefix=title_prefix)],
        geometry=DocumentGeometry(geom=geom, geom_detail=geom_detail),
        **fields,
    )


def _error_names(response):
    return [error['name'] for error in response.json['errors']]


def test_geohash_center():
    lon, lat = _geohash_center('u09tun')

    assert lon == pytest.approx(2.29, abs=0.1)
    assert lat == pytest.approx(48.86, abs=0.1)


def test_lon_lat_to_3857():
    x, y = _lon_lat_to_3857(0, 0)

    assert x == pytest.approx(0, abs=1e-6)
    assert y == pytest.approx(0, abs=1e-6)
    assert _lon_lat_to_3857(180, 0)[0] == pytest.approx(20037508.34, abs=0.1)


def _viewport(zoom, y=5700000):
    """Return the bbox of a map 680 pixels wide at the zoom (Alps latitude)."""
    width = 680 * 156543.03 / 2**zoom
    return (0, y - width / 2, width, y + width / 2)


@pytest.mark.parametrize(
    ('zoom', 'precision'),
    [(3, 4), (4, 4), (6, 5), (8, 6), (11, 7), (13, 8), (16, 9), (18, 9)],
)
def test_heatmap_precision_follows_the_box(zoom, precision):
    # cells of a few pixels whatever the zoom: finer cells for a smaller box
    assert _heatmap_precision(_viewport(zoom)) == precision


def test_heatmap_precision_is_bounded():
    world = (-20037508, -20037508, 20037508, 20037508)

    # the whole world cannot be asked in fine cells
    assert _heatmap_precision(world) == 3
    assert _heatmap_precision((0, 5700000, 100, 5700100)) == 9


@pytest.fixture
def outings(session):
    """Add three outings in the box and one far away (without a track)."""
    session.add(_outing('Hike 1', ['hiking'], 1, 'SRID=3857;POINT(635956 5723604)'))
    session.add(_outing('Hike 2', ['hiking'], 2, 'SRID=3857;POINT(635960 5723610)'))
    session.add(
        _outing('Ski tour', ['skitouring'], 3, 'SRID=3857;POINT(635960 5723620)')
    )
    session.add(_outing('Far away hike', ['hiking'], 4, 'SRID=3857;POINT(0 0)'))
    session.flush()
    reset_search_index(session)


def _count(response):
    return sum(bucket['count'] for bucket in response.json['buckets'])


def test_outings_heatmap_missing_bbox(client):
    response = client.get('/outings/map/heatmap', status=400)

    assert 'bbox' in _error_names(response)


def test_outings_heatmap_invalid_bbox(client):
    response = client.get('/outings/map/heatmap?bbox=1,2,3', status=400)

    assert 'bbox' in _error_names(response)


def test_outings_heatmap(client, outings):
    response = client.get(f'/outings/map/heatmap?bbox={BBOX}', status=200)

    # only the 3 outings within the bbox are counted, not the one at (0, 0)
    assert _count(response) == 3


def test_outings_heatmap_zoomed_in(client, outings):
    # a small box, so fine cells
    bbox = '635900,5723550,636000,5723650'
    response = client.get(f'/outings/map/heatmap?bbox={bbox}', status=200)

    assert _count(response) == 3
    # whole meters
    assert all(isinstance(bucket['x'], int) for bucket in response.json['buckets'])


def test_outings_heatmap_beyond_the_world(client, outings):
    # a map zoomed out far shows more than the world of the projection
    bbox = '-30000000,-30000000,30000000,30000000'
    response = client.get(f'/outings/map/heatmap?bbox={bbox}', status=200)

    assert _count(response) == 4


def test_outings_heatmap_still_accepts_zoom(client, outings):
    # the parameter of the first version: ignored, not a filter
    response = client.get(f'/outings/map/heatmap?bbox={BBOX}&zoom=8', status=200)

    assert _count(response) == 3


def test_outings_heatmap_over_the_meridian(client, session):
    # a box with a 0 in it (the Greenwich meridian is x = 0) is still a box
    session.add(_outing('Near', ['hiking'], 1, 'SRID=3857;POINT(50000 5700000)'))
    session.add(_outing('Far', ['hiking'], 2, 'SRID=3857;POINT(3000000 5700000)'))
    session.flush()
    reset_search_index(session)

    response = client.get(
        '/outings/map/heatmap?bbox=0,5600000,100000,5800000', status=200
    )

    assert _count(response) == 1


def test_outings_heatmap_ignores_the_sort_of_the_listing(client, outings):
    # `sort` on an unknown field is an error of the search index
    url = f'/outings/map/heatmap?bbox={BBOX}&sort=nothing&offset=30&limit=5'

    assert _count(client.get(url, status=200)) == 3


@pytest.mark.parametrize('ids', ['abc', '1,x', '²', '99999999999', '1.5', '-1'])
@pytest.mark.parametrize('path', ['heatmap', 'tracks'])
def test_invalid_ids(client, path, ids):
    response = client.get(f'/routes/map/{path}?bbox={BBOX}&ids={ids}', status=400)

    assert 'ids' in _error_names(response)


def test_too_many_ids(client):
    ids = ','.join(str(i) for i in range(1, 502))
    response = client.get(f'/routes/map/tracks?bbox={BBOX}&ids={ids}', status=400)

    assert 'ids' in _error_names(response)


def test_ids_may_be_empty_or_end_with_a_comma(client, routes):
    for ids in ('', ','):
        body = client.get(f'/routes/map/tracks?bbox={BBOX}&ids={ids}', status=200).json
        assert body['documents'] == []


def test_outings_heatmap_filtered_by_activity(client, outings):
    url = f'/outings/map/heatmap?bbox={BBOX}&act=skitouring'

    assert _count(client.get(url, status=200)) == 1


def test_outings_heatmap_filtered_by_date(client, outings):
    url = f'/outings/map/heatmap?bbox={BBOX}&date=2016-01-01,2016-01-02'

    assert _count(client.get(url, status=200)) == 2


@pytest.fixture
def tracks(session, user_ids):
    """Add outings with and without track, and the route of the first one."""
    outing1 = _outing(
        'Hike 1',
        ['hiking'],
        1,
        'SRID=3857;POINT(635956 5723604)',
        'SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        global_rating='AD',
        ski_rating='3.2',
    )
    session.add(outing1)
    session.add(
        _outing(
            'Ski tour',
            ['skitouring'],
            2,
            'SRID=3857;POINT(635960 5723610)',
            'SRID=3857;LINESTRING(635960 5723610, 635970 5723650)',
        )
    )
    # no geom_detail: must never be returned by the tracks endpoint
    session.add(_outing('No track', ['hiking'], 3, 'SRID=3857;POINT(635958 5723606)'))
    # the representative point is out of the bbox, but the track crosses it
    session.add(
        _outing(
            'Long hike',
            ['hiking'],
            4,
            'SRID=3857;POINT(634800 5723500)',
            'SRID=3857;LINESTRING(634800 5723500, 635500 5723500)',
        )
    )
    route = _route('Route', ['hiking'], 'SRID=3857;POINT(635956 5723604)')
    session.add(route)
    session.flush()

    association = Association.create(parent_document=route, child_document=outing1)
    session.add(association)
    session.add(association.get_log(user_ids['contributor'], is_creation=True))
    session.flush()
    reset_search_index(session)
    return outing1, route


def test_outings_tracks_missing_bbox(client):
    response = client.get('/outings/map/tracks', status=400)

    assert 'bbox' in _error_names(response)


def test_outings_tracks(client, tracks):
    body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert not body['truncated']
    assert {o['title'] for o in body['documents']} == {
        'Hike 1',
        'Ski tour',
        'Long hike',
    }
    for outing in body['documents']:
        assert outing['type'] == 'o'
        assert 'geom_detail' in outing['geometry']


@pytest.mark.parametrize('path', ['heatmap', 'tracks'])
def test_answers_can_be_cached(client, tracks, path):
    response = client.get(f'/outings/map/{path}?bbox={BBOX}', status=200)

    assert response.headers['Cache-Control'] == 'public, max-age=60'
    # the answer depends on the origin (CORS): a shared cache keeps one per origin
    assert 'Origin' in response.headers['Vary']


@pytest.mark.parametrize('origin', [None, 'http://localhost:6553'])
def test_cached_answers_differ_by_origin(client, tracks, origin):
    headers = {'Origin': origin} if origin else {}
    response = client.get(f'/outings/map/tracks?bbox={BBOX}', headers=headers)

    assert 'Origin' in response.headers['Vary']
    assert ('Access-Control-Allow-Origin' in response.headers) == bool(origin)


def test_errors_are_not_cached(client):
    response = client.get('/outings/map/tracks?bbox=x', status=400)

    assert 'max-age' not in response.headers.get('Cache-Control', '')


def test_outings_tracks_most_recent_first(client, tracks):
    body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert [o['title'] for o in body['documents']] == [
        'Long hike',
        'Ski tour',
        'Hike 1',
    ]
    assert [o['date_end'] for o in body['documents']] == [
        '2016-01-04',
        '2016-01-02',
        '2016-01-01',
    ]


def test_outings_tracks_tell_them_apart(client, tracks):
    body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json
    by_title = {o['title']: o for o in body['documents']}

    hike = by_title['Hike 1']
    assert hike['activities'] == ['hiking']
    assert hike['date_start'] == '2016-01-01'
    assert hike['global_rating'] == 'AD'
    assert hike['ski_rating'] == '3.2'
    # what is not set is not sent
    assert 'ice_rating' not in hike
    assert 'aid_rating' not in hike


def test_outings_tracks_filtered_by_activity(client, tracks):
    body = client.get(
        f'/outings/map/tracks?bbox={BBOX}&act=skitouring', status=200
    ).json

    assert [o['title'] for o in body['documents']] == ['Ski tour']


def test_outings_tracks_filtered_by_route(client, tracks):
    outing, route = tracks
    url = f'/outings/map/tracks?bbox={BBOX}&r={route.document_id}'
    body = client.get(url, status=200).json

    assert [o['document_id'] for o in body['documents']] == [outing.document_id]


def test_outings_tracks_filtered_by_several_routes(client, session, user_ids, tracks):
    # an outing can be linked to several routes: the outings of any of them
    outing1, route1 = tracks
    ski_tour = (
        session.query(Outing)
        .filter(Outing.locales.any(OutingLocale.title == 'Ski tour'))
        .one()
    )
    route2 = _route('Second route', ['hiking'], 'SRID=3857;POINT(635960 5723610)')
    session.add(route2)
    session.flush()
    for route, outing in ((route2, ski_tour), (route2, outing1)):
        association = Association.create(parent_document=route, child_document=outing)
        session.add(association)
        session.add(association.get_log(user_ids['contributor'], is_creation=True))
    session.flush()
    # the routes of "Hike 1" were read when the first route was linked
    session.expire_all()
    reset_search_index(session)

    def titles(routes):
        url = f'/outings/map/tracks?bbox={BBOX}&r={routes}'
        return {o['title'] for o in client.get(url, status=200).json['documents']}

    # "Long hike" has no route
    assert titles(route2.document_id) == {'Hike 1', 'Ski tour'}
    assert titles(route1.document_id) == {'Hike 1'}
    assert titles(f'{route1.document_id},{route2.document_id}') == {
        'Hike 1',
        'Ski tour',
    }


@pytest.mark.parametrize(
    ('value', 'limit'),
    [
        (None, 100),
        ('', 100),
        ('250', 250),
        (' 250 ', 250),
        ('1', 1),
        ('0', 100),
        ('-5', 100),
        ('many', 100),
        ('2.5', 100),
        ('100000', 500),
    ],
)
def test_tracks_limit(monkeypatch, value, limit):
    if value is None:
        monkeypatch.delenv('TRACKS_OVERLAY_MAX_TRACKS', raising=False)
    else:
        monkeypatch.setenv('TRACKS_OVERLAY_MAX_TRACKS', value)

    assert tracks_limit() == limit


def test_outings_tracks_limit_from_the_environment(client, monkeypatch, tracks):
    url = f'/outings/map/tracks?bbox={BBOX}'

    monkeypatch.setenv('TRACKS_OVERLAY_MAX_TRACKS', '2')
    assert client.get(url, status=200).json['truncated']

    # 3 tracks cross the box
    monkeypatch.setenv('TRACKS_OVERLAY_MAX_TRACKS', '3')
    body = client.get(url, status=200).json
    assert not body['truncated']
    assert len(body['documents']) == 3


def test_outings_tracks_truncated(client, tracks):
    with patch('c2corg_api.views.document_map.TRACKS_LIMIT_MAX', 1):
        body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert body['truncated']
    assert body['documents'] == []


def test_outings_tracks_truncated_by_candidates(client, tracks):
    # filters that match many documents: the database candidates are capped
    with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 1):
        url = f'/outings/map/tracks?bbox={BBOX}&act=hiking'
        body = client.get(url, status=200).json

    assert body['truncated']
    assert body['documents'] == []


def test_outings_tracks_with_selective_filters_beat_the_cap(client, tracks):
    # a filter that matches few documents (the outings of a route) is
    # answered from them, however many tracks there are in the view
    outing, route = tracks
    with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 1):
        url = f'/outings/map/tracks?bbox={BBOX}&r={route.document_id}'
        body = client.get(url, status=200).json

    assert not body['truncated']
    assert [o['document_id'] for o in body['documents']] == [outing.document_id]


def test_outings_tracks_without_filters_stop_at_the_limit(client, tracks):
    # no search index, and no need to look at more than `limit + 1` tracks
    with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 1):
        body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert not body['truncated']
    assert len(body['documents']) == 3


def test_a_track_next_to_the_view_is_not_returned(client, session):
    # the box of the track crosses the view, the track does not
    session.add(
        _outing(
            'Diagonal',
            ['hiking'],
            1,
            'SRID=3857;POINT(635000 5723000)',
            'SRID=3857;LINESTRING(635000 5723000, 636000 5724000)',
        )
    )
    session.flush()
    reset_search_index(session)

    body = client.get('/outings/map/tracks?bbox=635700,5723000,636000,5723300').json

    assert body['documents'] == []
    assert not body['truncated']


def test_outings_tracks_count_only_the_documents_with_a_track(client, tracks):
    # 4 outings are around, one has no track: 3 are looked at
    with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 3):
        body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert not body['truncated']
    assert len(body['documents']) == 3


def test_outings_tracks_do_not_search_without_filters(client, tracks):
    with patch(
        'c2corg_api.views.document_map.build_query', wraps=build_query
    ) as search:
        client.get(f'/outings/map/tracks?bbox={BBOX}&pl=fr', status=200)
        search.assert_not_called()

        client.get(f'/outings/map/tracks?bbox={BBOX}&act=hiking', status=200)
        search.assert_called_once()


def test_outings_tracks_found_by_their_track_not_by_their_point(client, tracks):
    # the point of "Long hike" is out of this box, its track crosses it
    bbox = '635400,5723400,635600,5723600'
    body = client.get(f'/outings/map/tracks?bbox={bbox}', status=200).json

    assert [o['title'] for o in body['documents']] == ['Long hike']


@pytest.fixture
def long_tracks(session):
    """Add outings whose tracks have many points, in 3D, and a bend."""
    line = ', '.join(
        f'{635000 + i} {5723000 + i // 2} {1000 + i}' for i in range(0, 2000, 4)
    )
    session.add(
        _outing(
            'Straight',
            ['hiking'],
            1,
            'SRID=3857;POINT(635000 5723000)',
            f'SRID=3857;LINESTRING({line})',
        )
    )
    session.add(
        _outing(
            'Bend',
            ['hiking'],
            2,
            'SRID=3857;POINT(635000 5723000)',
            'SRID=3857;LINESTRING(635000 5723000, 635500 5723400, 636000 5723000)',
        )
    )
    session.flush()
    reset_search_index(session)


def test_outings_tracks_are_simplified_and_in_2d(client, long_tracks):
    body = client.get('/outings/map/tracks?bbox=634000,5722000,637000,5725000').json
    tracks = {
        o['title']: json.loads(o['geometry']['geom_detail']) for o in body['documents']
    }

    # 500 points on a straight line: its ends
    assert len(tracks['Straight']['coordinates']) == 2
    assert tracks['Straight']['coordinates'][0] == [635000, 5723000]
    # what is a bend of the track stays
    assert len(tracks['Bend']['coordinates']) == 3
    # no elevation, no CRS, whole meters for a box of this size
    assert all(len(point) == 2 for point in tracks['Bend']['coordinates'])
    assert 'crs' not in tracks['Bend']
    assert all(isinstance(value, int) for value in tracks['Bend']['coordinates'][1])


@pytest.fixture
def wiggle(session):
    """Add an outing whose track has a bend of 8 meters."""
    # (the database already simplifies the tracks of routes and outings by 5 m
    # when it saves them, see simplify_geom_detail: the bend is more than that)
    session.add(
        _outing(
            'Wiggle',
            ['hiking'],
            1,
            'SRID=3857;POINT(635100 5723000)',
            'SRID=3857;LINESTRING(635000 5723000, 635100 5723008, 635200 5723000)',
        )
    )
    session.flush()
    reset_search_index(session)


def _wiggle_points(client, bbox):
    body = client.get(f'/outings/map/tracks?bbox={bbox}', status=200).json
    return json.loads(body['documents'][0]['geometry']['geom_detail'])['coordinates']


def test_tracks_are_simplified_for_the_size_of_the_box(client, wiggle):
    # about a pixel of the map: a bend of 8 m is nothing for a box of 13.5 km
    # (9 m), but is seen in one of 600 m (0.4 m, and a decimal)
    assert len(_wiggle_points(client, '628000,5716000,641500,5729500')) == 2
    assert _wiggle_points(client, '634900,5722900,635500,5723100') == [
        [635000, 5723000],
        [635100, 5723008],
        [635200, 5723000],
    ]


def test_a_track_that_collapses_is_still_there(client, session):
    # a 30 m loop survives the 5 m simplification of the database trigger, but
    # not the 100 m tolerance of a 150 km wide box: it would be NULL
    session.add(
        _outing(
            'Loop',
            ['hiking'],
            1,
            'SRID=3857;POINT(635000 5723000)',
            'SRID=3857;LINESTRING(635000 5723000, 635030 5723030, 635000 5723000)',
        )
    )
    session.flush()
    reset_search_index(session)

    body = client.get('/outings/map/tracks?bbox=560000,5650000,710000,5800000').json

    assert [o['title'] for o in body['documents']] == ['Loop']
    coordinates = json.loads(body['documents'][0]['geometry']['geom_detail'])
    assert coordinates['coordinates'][0] == [635000, 5723000]


@pytest.fixture
def routes(session):
    """Add two routes with a track in the box and one far away."""
    session.add(
        _route(
            'Hike route',
            ['hiking'],
            'SRID=3857;POINT(635956 5723604)',
            'SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            title_prefix='Mont Blanc',
            global_rating='D',
            hiking_rating='T3',
        )
    )
    session.add(
        _route(
            'Ski route',
            ['skitouring'],
            'SRID=3857;POINT(635960 5723610)',
            'SRID=3857;LINESTRING(635960 5723610, 635970 5723650)',
        )
    )
    session.add(
        _route(
            'Far away route',
            ['hiking'],
            'SRID=3857;POINT(0 0)',
            'SRID=3857;LINESTRING(0 0, 10 10)',
        )
    )
    session.flush()
    reset_search_index(session)


def test_routes_heatmap(client, routes):
    response = client.get(f'/routes/map/heatmap?bbox={BBOX}', status=200)

    assert _count(response) == 2


def test_routes_heatmap_filtered_by_activity(client, routes):
    url = f'/routes/map/heatmap?bbox={BBOX}&act=skitouring'

    assert _count(client.get(url, status=200)) == 1


def test_routes_tracks(client, routes):
    body = client.get(f'/routes/map/tracks?bbox={BBOX}', status=200).json

    assert not body['truncated']
    assert {r['title'] for r in body['documents']} == {
        'Mont Blanc : Hike route',
        'Ski route',
    }
    assert {r['type'] for r in body['documents']} == {'r'}


def test_routes_tracks_tell_them_apart(client, routes):
    body = client.get(f'/routes/map/tracks?bbox={BBOX}', status=200).json
    route = next(r for r in body['documents'] if r['title'].endswith('Hike route'))

    assert route['activities'] == ['hiking']
    assert route['global_rating'] == 'D'
    assert route['hiking_rating'] == 'T3'
    assert 'date_end' not in route


def test_routes_tracks_filtered_by_activity(client, routes):
    body = client.get(f'/routes/map/tracks?bbox={BBOX}&act=hiking', status=200).json

    assert [r['title'] for r in body['documents']] == ['Mont Blanc : Hike route']


def test_routes_tracks_filtered_by_ids(client, session, routes):
    route = (
        session.query(Route)
        .filter(Route.locales.any(RouteLocale.title == 'Ski route'))
        .one()
    )
    url = f'/routes/map/tracks?bbox={BBOX}&ids={route.document_id}'
    body = client.get(url, status=200).json

    assert [r['document_id'] for r in body['documents']] == [route.document_id]


def test_routes_tracks_filtered_by_empty_ids(client, routes):
    body = client.get(f'/routes/map/tracks?bbox={BBOX}&ids=', status=200).json

    assert body['documents'] == []


@pytest.mark.parametrize('value', [None, '', 'true', 'TRUE', '1', 'yes', 'on', 'oui'])
def test_tracks_overlay_enabled(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('TRACKS_OVERLAY_ENABLED', raising=False)
    else:
        monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', value)

    assert tracks_overlay_enabled()


@pytest.mark.parametrize(
    'value', ['false', 'False', 'FALSE', ' false ', '0', 'no', 'off']
)
def test_tracks_overlay_disabled(monkeypatch, value):
    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', value)

    assert not tracks_overlay_enabled()


@pytest.mark.parametrize(
    'path',
    [
        '/outings/map/heatmap',
        '/outings/map/tracks',
        '/routes/map/heatmap',
        '/routes/map/tracks',
    ],
)
def test_overlays_turned_off(client, monkeypatch, path):
    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'false')

    # a 503 before anything else: not even the missing box is reported
    response = client.get(path, status=503)

    assert response.json['errors'][0]['name'] == 'Service Unavailable'


def test_overlays_turned_off_do_not_search(client, monkeypatch):
    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'false')

    with patch('c2corg_api.views.document_map.build_query') as build_query:
        client.get(f'/outings/map/tracks?bbox={BBOX}', status=503)
        client.get(f'/routes/map/heatmap?bbox={BBOX}', status=503)

    build_query.assert_not_called()


def test_overlays_turned_on_again(client, monkeypatch):
    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'false')
    client.get(f'/outings/map/tracks?bbox={BBOX}', status=503)

    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'true')
    client.get(f'/outings/map/tracks?bbox={BBOX}', status=200)
