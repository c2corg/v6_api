from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import reset_cache_key


def _add_waypoint(session):
    waypoint = Waypoint(
        waypoint_type='summit',
        elevation=2000,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[WaypointLocale(lang='fr', title='Mont Granier')],
    )
    session.add(waypoint)
    session.flush()
    return waypoint


def test_listing_total_is_cached(client, session):
    _add_waypoint(session)
    total = client.get('/waypoints').json['total']
    assert total > 0

    # a new document does not change the cached total
    _add_waypoint(session)
    assert client.get('/waypoints').json['total'] == total

    # it does once the cached value is gone (a new cache key here)
    reset_cache_key()
    assert client.get('/waypoints').json['total'] == total + 1


def test_listing_total_per_type(client, session):
    _add_waypoint(session)
    assert client.get('/waypoints').json['total'] > 0

    # the waypoints' total is not the routes' total
    assert client.get('/routes').json['total'] == 0
