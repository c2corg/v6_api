from c2corg_api.models.association import AssociationLog
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


def _add_association_log(session, user_ids, parent, child):
    session.add(
        AssociationLog(
            parent_document_id=parent.document_id,
            parent_document_type=parent.type,
            child_document_id=child.document_id,
            child_document_type=child.type,
            user_id=user_ids['contributor'],
            is_creation=True,
        )
    )
    session.flush()


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


def test_associations_history_count_is_cached(client, session, user_ids):
    waypoint1 = _add_waypoint(session)
    waypoint2 = _add_waypoint(session)
    _add_association_log(session, user_ids, waypoint1, waypoint2)
    count = client.get('/associations-history').json['count']
    assert count > 0

    _add_association_log(session, user_ids, waypoint2, waypoint1)
    assert client.get('/associations-history').json['count'] == count

    reset_cache_key()
    assert client.get('/associations-history').json['count'] == count + 1


def test_associations_history_count_of_a_document_is_not_cached(
    client, session, user_ids
):
    waypoint1 = _add_waypoint(session)
    waypoint2 = _add_waypoint(session)
    _add_association_log(session, user_ids, waypoint1, waypoint2)
    url = f'/associations-history?d={waypoint1.document_id}'
    assert client.get(url).json['count'] == 1

    _add_association_log(session, user_ids, waypoint2, waypoint1)
    assert client.get(url).json['count'] == 2
