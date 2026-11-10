import datetime
from dataclasses import dataclass

import pytest
from pyproj import Transformer

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.tests import encode_polyline
from c2corg_api.views.route_suggestion import decode_polyline

TO_3857 = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)

# the GPS track: about 4.5 km to the north, from an access to a summit
ACCESS = (6.86, 45.90)
SUMMIT = (6.88, 45.94)
TRACK = [ACCESS, (6.87, 45.92), SUMMIT]


def point(lon, lat):
    x, y = TO_3857.transform(lon, lat)
    return f'SRID=3857;POINT({x} {y})'


def line(points):
    xy = ', '.join('{} {}'.format(*TO_3857.transform(lon, lat)) for lon, lat in points)
    return f'SRID=3857;LINESTRING({xy})'


@dataclass
class Docs:
    """The routes around the track, built by `docs`."""

    on_track: Route
    same_summit: Route
    same_summit_popular: Route
    beside: Route
    far: Route


@pytest.fixture
def docs(session) -> Docs:
    summit = add_waypoint(session, 'summit', SUMMIT)
    access = add_waypoint(session, 'access', ACCESS)
    # another access, 1.5 km to the east of the track
    other_access = add_waypoint(session, 'access', (6.89, 45.90))
    # a summit 1 km to the west of the track
    other_summit = add_waypoint(session, 'summit', (6.857, 45.93))
    far_summit = add_waypoint(session, 'summit', (7.0, 46.0))
    # its track follows the GPS track
    on_track = add_route(
        session, 'skitouring', summit, [summit, access], geom_detail=line(TRACK)
    )
    # to the same summit from another access, no track: twice, one with outings
    same_summit = add_route(session, 'skitouring', summit, [summit, other_access])
    same_summit_popular = add_route(
        session, 'skitouring', summit, [summit, other_access]
    )
    for _ in range(5):
        add_outing(session, same_summit_popular)
    beside = add_route(session, 'hiking', other_summit, [other_summit])
    far = add_route(session, 'skitouring', far_summit, [far_summit])
    session.flush()
    return Docs(on_track, same_summit, same_summit_popular, beside, far)


def add_waypoint(session, waypoint_type, lon_lat):
    waypoint = Waypoint(
        waypoint_type=waypoint_type,
        elevation=2000,
        geometry=DocumentGeometry(geom=point(*lon_lat)),
    )
    session.add(waypoint)
    session.flush()
    return waypoint


def add_route(session, activity, main_waypoint, waypoints, geom_detail=None):
    # the point of a route is its main waypoint
    route = Route(
        activities=[activity],
        main_waypoint_id=main_waypoint.document_id,
        geometry=DocumentGeometry(
            geom=session.get(DocumentGeometry, main_waypoint.document_id).geom,
            geom_detail=geom_detail,
        ),
        locales=[RouteLocale(lang='fr', title='Voie')],
    )
    session.add(route)
    session.flush()
    for waypoint in waypoints:
        session.add(
            Association(
                parent_document_id=waypoint.document_id,
                parent_document_type=WAYPOINT_TYPE,
                child_document_id=route.document_id,
                child_document_type=ROUTE_TYPE,
            )
        )
    return route


def add_outing(session, route):
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2026, 1, 1),
        date_end=datetime.date(2026, 1, 1),
    )
    session.add(outing)
    session.flush()
    session.add(
        Association(
            parent_document_id=route.document_id,
            parent_document_type=ROUTE_TYPE,
            child_document_id=outing.document_id,
            child_document_type=OUTING_TYPE,
        )
    )


def suggested(client, status=200, **params):
    params.setdefault('track', encode_polyline(TRACK))
    return client.get('/routes/suggest', params=params, status=status).json


def suggested_ids(client, **params):
    body = suggested(client, **params)
    ids = [d['document_id'] for d in body['documents']]
    assert body['total'] == len(ids)
    return ids


def test_best_first(client, docs):
    # the route along the track, then those to its summit (the one with
    # outings first), then the one beside it; not the far one
    assert suggested_ids(client) == [
        docs.on_track.document_id,
        docs.same_summit_popular.document_id,
        docs.same_summit.document_id,
        docs.beside.document_id,
    ]


def test_listing_documents(client, docs):
    body = suggested(client, pl='fr', limit=1)
    assert body['total'] == 1
    (route,) = body['documents']
    assert route['document_id'] == docs.on_track.document_id
    assert route['locales'][0]['title'] == 'Voie'
    assert route['activities'] == ['skitouring']


def test_activities(client, docs):
    assert suggested_ids(client, act='hiking') == [docs.beside.document_id]
    assert len(suggested_ids(client, act='hiking,skitouring')) == 4
    assert suggested_ids(client, act='paragliding') == []


def test_no_route_near(client, docs):
    assert (
        suggested_ids(client, track=encode_polyline([(2.0, 45.0), (2.1, 45.1)])) == []
    )


@pytest.mark.parametrize(
    'params, name',
    [
        ({'track': 'not a polyline ~'}, 'track'),
        ({'track': encode_polyline([ACCESS])}, 'track'),
        ({'track': encode_polyline([(200.0, 45.0), (6.0, 45.0)])}, 'track'),
        ({'act': 'flying'}, 'act'),
        ({'limit': 'many'}, 'limit'),
    ],
)
def test_invalid(client, params, name):
    # FastAPI's answer to invalid parameters (#2546)
    (error,) = suggested(client, status=422, **params)['detail']
    assert (error['loc'], error['msg']) == (['query', name], f'invalid {name}')


def test_track_required(client):
    (error,) = client.get('/routes/suggest', status=422).json['detail']
    assert (error['loc'], error['type']) == (['query', 'track'], 'missing')


def test_decode_polyline():
    # the example of Google's documentation of the format
    assert decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@') == [
        (-120.2, 38.5),
        (-120.95, 40.7),
        (-126.453, 43.252),
    ]
    assert decode_polyline(encode_polyline(TRACK)) == TRACK


@pytest.mark.parametrize('encoded', ['_p~iF', '_p~iF~ps|', 'é'])
def test_decode_polyline_invalid(encoded):
    with pytest.raises(ValueError):
        decode_polyline(encoded)
