from datetime import date
from unittest.mock import patch

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.tests.search import reset_search_index
from c2corg_api.views.document_map import (
    _geohash_center,
    _heatmap_precision,
    _lon_lat_to_3857,
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


@pytest.mark.parametrize(
    ('zoom', 'precision'),
    [
        (0, 2),
        (3, 3),
        (4, 4),
        (5, 4),
        (6, 5),
        (8, 5),
        (9, 6),
        (10, 6),
        (11, 7),
        (13, 7),
        (14, 8),
        (30, 8),
    ],
)
def test_heatmap_precision(zoom, precision):
    assert _heatmap_precision(zoom) == precision


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
    response = client.get('/outings/map/heatmap?zoom=8', status=400)

    assert 'bbox' in _error_names(response)


def test_outings_heatmap_missing_zoom(client):
    response = client.get(f'/outings/map/heatmap?bbox={BBOX}', status=400)

    assert 'zoom' in _error_names(response)


def test_outings_heatmap_invalid_bbox(client):
    response = client.get('/outings/map/heatmap?bbox=1,2,3&zoom=8', status=400)

    assert 'bbox' in _error_names(response)


def test_outings_heatmap(client, outings):
    response = client.get(f'/outings/map/heatmap?bbox={BBOX}&zoom=8', status=200)

    # only the 3 outings within the bbox are counted, not the one at (0, 0)
    assert _count(response) == 3


def test_outings_heatmap_zoomed_in(client, outings):
    response = client.get(f'/outings/map/heatmap?bbox={BBOX}&zoom=16', status=200)

    assert _count(response) == 3
    # whole meters
    assert all(isinstance(bucket['x'], int) for bucket in response.json['buckets'])


def test_outings_heatmap_filtered_by_activity(client, outings):
    url = f'/outings/map/heatmap?bbox={BBOX}&zoom=8&act=skitouring'

    assert _count(client.get(url, status=200)) == 1


def test_outings_heatmap_filtered_by_date(client, outings):
    url = f'/outings/map/heatmap?bbox={BBOX}&zoom=8&date=2016-01-01,2016-01-02'

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


def test_outings_tracks_truncated(client, tracks):
    with patch('c2corg_api.views.document_map.TRACKS_LIMIT_MAX', 1):
        body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert body['truncated']
    assert body['documents'] == []


def test_outings_tracks_truncated_by_candidates(client, tracks):
    with patch('c2corg_api.views.document_map.TRACKS_CANDIDATES_MAX', 1):
        body = client.get(f'/outings/map/tracks?bbox={BBOX}', status=200).json

    assert body['truncated']
    assert body['documents'] == []


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
    response = client.get(f'/routes/map/heatmap?bbox={BBOX}&zoom=8', status=200)

    assert _count(response) == 2


def test_routes_heatmap_filtered_by_activity(client, routes):
    url = f'/routes/map/heatmap?bbox={BBOX}&zoom=8&act=skitouring'

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
        client.get(f'/routes/map/heatmap?bbox={BBOX}&zoom=8', status=503)

    build_query.assert_not_called()


def test_overlays_turned_on_again(client, monkeypatch):
    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'false')
    client.get(f'/outings/map/tracks?bbox={BBOX}', status=503)

    monkeypatch.setenv('TRACKS_OVERLAY_ENABLED', 'true')
    client.get(f'/outings/map/tracks?bbox={BBOX}', status=200)
