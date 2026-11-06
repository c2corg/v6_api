from dataclasses import dataclass
from unittest.mock import patch

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.search import reset_search_index
from c2corg_api.views.route import get_routes_reachable_ids
from c2corg_api.views.waypoint import build_reachable_waypoints_query

POINT = 'SRID=3857;POINT(635961 5723624)'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    area: Area
    access: Waypoint
    summit: Waypoint
    hiking1: Route
    hiking2: Route
    skitouring: Route
    not_reachable: Route


@pytest.fixture
def docs(session) -> Docs:
    area = Area(area_type='range', locales=[DocumentLocale(lang='fr', title='A')])
    session.add(area)
    session.flush()
    access = add_waypoint(session, area, 'access', 'Arret')
    summit = add_waypoint(session, area, 'summit', 'Sommet')
    stoparea = Stoparea(
        navitia_id='stop_area:1',
        stoparea_name='Arret',
        line='1',
        operator='Bus',
        geom=POINT,
    )
    session.add(stoparea)
    session.flush()
    # the stop areas make the access waypoint and the summit reachable,
    # but only an access waypoint makes its routes reachable
    for waypoint in (access, summit):
        session.add(
            WaypointStoparea(
                waypoint_id=waypoint.document_id,
                stoparea_id=stoparea.stoparea_id,
                distance=10,
            )
        )

    hiking1 = add_route(session, area, 'hiking', 'Boucle 1', access)
    hiking2 = add_route(session, area, 'hiking', 'Boucle 2', access)
    # the association in the other direction: the route is the parent
    skitouring = add_route(session, area, 'skitouring', 'Ski', access, reverse=True)
    # linked to the summit only: not reachable
    not_reachable = add_route(session, area, 'hiking', 'Sommet', summit)
    session.flush()
    reset_search_index(session)
    return Docs(
        area=area,
        access=access,
        summit=summit,
        hiking1=hiking1,
        hiking2=hiking2,
        skitouring=skitouring,
        not_reachable=not_reachable,
    )


def add_waypoint(session, area, waypoint_type, title):
    waypoint = Waypoint(
        waypoint_type=waypoint_type,
        elevation=900,
        geometry=DocumentGeometry(geom=POINT),
        locales=[DocumentLocale(lang='fr', title=title)],
    )
    session.add(waypoint)
    session.flush()
    in_area(session, area, waypoint)
    return waypoint


def add_route(session, area, activity, title, waypoint, reverse=False):
    route = Route(
        activities=[activity],
        geometry=DocumentGeometry(geom=POINT),
        locales=[RouteLocale(lang='fr', title=title)],
    )
    session.add(route)
    session.flush()
    parent, child = (route, waypoint) if reverse else (waypoint, route)
    session.add(
        Association(
            parent_document_id=parent.document_id,
            parent_document_type=ROUTE_TYPE if reverse else WAYPOINT_TYPE,
            child_document_id=child.document_id,
            child_document_type=WAYPOINT_TYPE if reverse else ROUTE_TYPE,
        )
    )
    in_area(session, area, route)
    return route


def in_area(session, area, document):
    session.add(
        AreaAssociation(document_id=document.document_id, area_id=area.document_id)
    )


def get_ids(docs, client, path, **params):
    body = client.get(path, params=params, status=200).json
    for document in body['documents']:
        assert [a['document_id'] for a in document['areas']] == [docs.area.document_id]
    return [d['document_id'] for d in body['documents']], body['total']


def test_reachable_route_ids(docs):
    # both directions of the associations, access waypoints only
    assert get_routes_reachable_ids() == {
        docs.hiking1.document_id,
        docs.hiking2.document_id,
        docs.skitouring.document_id,
    }


def test_reachable_routes_paged(client, docs):
    # sorted by id, newest first, as the other listings
    reachable = [
        docs.skitouring.document_id,
        docs.hiking2.document_id,
        docs.hiking1.document_id,
    ]
    assert get_ids(docs, client, '/reachableroutes', limit=2) == (reachable[:2], 3)
    assert get_ids(docs, client, '/reachableroutes', limit=2, offset=2) == (
        reachable[2:],
        3,
    )
    assert get_ids(docs, client, '/reachableroutes', limit=2, offset=3) == ([], 3)


def test_reachable_routes_filtered(client, docs):
    ids, total = get_ids(docs, client, '/reachableroutes', act='skitouring')
    assert (ids, total) == ([docs.skitouring.document_id], 1)


def test_reachable_routes_beyond_the_window_of_elasticsearch(client, docs):
    # past the result window, the page comes from all the filtered ids
    expected = get_ids(docs, client, '/reachableroutes', limit=2, offset=1)
    with patch('c2corg_api.views.document.ES_MAX_RESULT_WINDOW', 2):
        assert get_ids(docs, client, '/reachableroutes', limit=2, offset=1) == expected


def test_reachable_waypoints_paged(client, docs):
    reachable = [docs.summit.document_id, docs.access.document_id]
    assert get_ids(docs, client, '/reachablewaypoints', limit=1) == (
        reachable[:1],
        2,
    )
    assert get_ids(docs, client, '/reachablewaypoints', limit=1, offset=1) == (
        reachable[1:],
        2,
    )


def test_navitia_waypoints_query_is_not_paged(docs):
    # the Navitia jobs need all the reachable waypoints
    query, total = build_reachable_waypoints_query(
        {}, {'offset': 0, 'limit': 1, 'lang': None}
    )
    ids = [waypoint.document_id for waypoint, _ in query.all()]
    assert (sorted(ids), total) == (
        sorted([docs.access.document_id, docs.summit.document_id]),
        2,
    )
