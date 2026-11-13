import datetime

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import (
    CacheVersion,
    update_cache_version,
    update_cache_version_associations,
    update_cache_version_for_area,
    update_cache_version_for_map,
)
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.views.document import create_new_version


def test_trigger_create_cache_version(session):
    waypoint = Waypoint(waypoint_type='summit')
    session.add(waypoint)
    session.flush()

    cache_version = session.get(CacheVersion, waypoint.document_id)
    assert cache_version is not None
    assert cache_version.version is not None
    assert cache_version.last_updated is not None


def test_update_cache_version_single_wp(session):
    waypoint = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    session.add_all([waypoint, waypoint_unrelated])
    session.flush()

    cache_version = session.get(CacheVersion, waypoint.document_id)
    cache_version.last_updated = datetime.datetime(2016, 1, 1, 12, 1, 0)
    session.flush()
    current_version = cache_version.version
    current_last_updated = cache_version.last_updated

    update_cache_version(waypoint)
    session.refresh(cache_version)
    assert cache_version.version == current_version + 1
    assert cache_version.last_updated != current_last_updated

    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)
    assert cache_version_untouched.version == 1


def test_update_cache_version_wp_with_associations(session):
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint3 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    session.add_all([waypoint1, waypoint2, waypoint3, waypoint_unrelated])
    session.flush()

    session.add(Association.create(waypoint1, waypoint2))
    session.add(Association.create(waypoint3, waypoint1))
    session.flush()

    update_cache_version(waypoint1)
    cache_version1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version2 = session.get(CacheVersion, waypoint1.document_id)
    cache_version3 = session.get(CacheVersion, waypoint1.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version1.version == 2
    assert cache_version2.version == 2
    assert cache_version3.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_wp_as_main_wp(session):
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint3 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    route = Route(main_waypoint=waypoint1, activities=['skitouring'])
    session.add_all([waypoint1, waypoint2, waypoint3, waypoint_unrelated, route])
    session.flush()

    session.add(Association.create(waypoint1, route))
    session.add(Association.create(waypoint2, route))
    session.add(Association.create(waypoint3, waypoint2))
    session.flush()

    update_cache_version(waypoint1)
    cache_version_wp1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version_wp2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version_wp3 = session.get(CacheVersion, waypoint3.document_id)
    cache_version_route = session.get(CacheVersion, route.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version_wp1.version == 3
    assert cache_version_wp2.version == 2
    assert cache_version_wp3.version == 2
    assert cache_version_route.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_route(session):
    route1 = Route(activities=['skitouring'])
    route2 = Route(activities=['skitouring'])
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    session.add_all([waypoint1, waypoint2, waypoint_unrelated, route1, route2])
    session.flush()

    session.add(Association.create(waypoint1, route1))
    session.add(Association.create(route2, route1))
    session.add(Association.create(waypoint2, waypoint1))
    session.flush()

    update_cache_version(route1)
    cache_version_route1 = session.get(CacheVersion, route1.document_id)
    cache_version_route2 = session.get(CacheVersion, route2.document_id)
    cache_version_wp1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version_wp2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version_route1.version == 2
    assert cache_version_route2.version == 2
    assert cache_version_wp1.version == 3
    assert cache_version_wp2.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_outing(session):
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 2, 1),
        date_end=datetime.date(2016, 2, 1),
    )
    route1 = Route(activities=['skitouring'])
    route2 = Route(activities=['skitouring'])
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    session.add_all([outing, waypoint1, waypoint2, waypoint_unrelated, route1, route2])
    session.flush()

    session.add(Association.create(route1, outing))
    session.add(Association.create(waypoint1, route1))
    session.add(Association.create(route2, outing))
    session.add(Association.create(waypoint2, waypoint1))
    session.flush()

    update_cache_version(outing)
    cache_version_outing = session.get(CacheVersion, outing.document_id)
    cache_version_route1 = session.get(CacheVersion, route1.document_id)
    cache_version_route2 = session.get(CacheVersion, route2.document_id)
    cache_version_wp1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version_wp2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version_outing.version == 2
    assert cache_version_route1.version == 2
    assert cache_version_route2.version == 2
    assert cache_version_wp1.version == 2
    assert cache_version_wp2.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_user(session):
    """Test that outings are invalidated if an user name changes."""
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 2, 1),
        date_end=datetime.date(2016, 2, 1),
    )
    user_profile = UserProfile()
    session.add_all([outing, user_profile])
    session.flush()

    session.add(Association.create(user_profile, outing))
    session.flush()

    update_cache_version(user_profile)
    cache_version_user_profile = session.get(CacheVersion, user_profile.document_id)
    cache_version_outing = session.get(CacheVersion, outing.document_id)

    assert cache_version_outing.version == 2
    assert cache_version_user_profile.version == 2


def test_update_cache_version_user_document_version(session):
    """Test that a document is invalidated if a user name of a user that
    edited one of the document versions is changed.
    """
    waypoint = Waypoint(
        waypoint_type='summit',
        elevation=2203,
        locales=[WaypointLocale(lang='en', title='...', description='...')],
    )

    user_profile = UserProfile()
    user = User(
        name='test_user',
        username='test_user',
        email='test_user@camptocamp.org',
        forum_username='testuser',
        password='test_user',
        email_validated=True,
        profile=user_profile,
    )
    session.add_all([waypoint, user_profile, user])
    session.flush()

    create_new_version(waypoint, user.id)

    update_cache_version(user_profile)
    cache_version_user_profile = session.get(CacheVersion, user_profile.document_id)
    cache_version_waypoint = session.get(CacheVersion, waypoint.document_id)

    assert cache_version_waypoint.version == 2
    assert cache_version_user_profile.version == 2


def test_update_cache_version_associations_removed_wp(session):
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint3 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    session.add_all([waypoint1, waypoint2, waypoint3, waypoint_unrelated])
    session.flush()

    update_cache_version_associations(
        [],
        [
            {
                'parent_id': waypoint1.document_id,
                'parent_type': WAYPOINT_TYPE,
                'child_id': waypoint2.document_id,
                'child_type': WAYPOINT_TYPE,
            },
            {
                'parent_id': waypoint3.document_id,
                'parent_type': WAYPOINT_TYPE,
                'child_id': waypoint1.document_id,
                'child_type': WAYPOINT_TYPE,
            },
        ],
    )

    cache_version1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version3 = session.get(CacheVersion, waypoint3.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version1.version == 2
    assert cache_version2.version == 2
    assert cache_version3.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_associations_removed_wp_route(session):
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint3 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    route = Route(activities=['skitouring'])
    session.add_all([waypoint1, waypoint2, waypoint3, waypoint_unrelated, route])
    session.flush()

    session.add(Association.create(waypoint2, waypoint1))
    session.add(Association.create(waypoint3, waypoint2))
    session.flush()

    update_cache_version_associations(
        [],
        [
            {
                'parent_id': waypoint1.document_id,
                'parent_type': WAYPOINT_TYPE,
                'child_id': route.document_id,
                'child_type': ROUTE_TYPE,
            }
        ],
    )

    cache_version1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version3 = session.get(CacheVersion, waypoint3.document_id)
    cache_version_route = session.get(CacheVersion, route.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version1.version == 2
    assert cache_version2.version == 2
    assert cache_version3.version == 2
    assert cache_version_route.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_associations_removed_route_outing(session):
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    waypoint3 = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    route = Route(activities=['skitouring'])
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 2, 1),
        date_end=datetime.date(2016, 2, 1),
    )
    session.add_all(
        [waypoint1, waypoint2, waypoint3, waypoint_unrelated, route, outing]
    )
    session.flush()

    session.add(Association.create(waypoint1, route))
    session.add(Association.create(waypoint2, waypoint1))
    session.add(Association.create(waypoint3, waypoint2))
    session.flush()

    update_cache_version_associations(
        [],
        [
            {
                'parent_id': route.document_id,
                'parent_type': ROUTE_TYPE,
                'child_id': outing.document_id,
                'child_type': OUTING_TYPE,
            }
        ],
    )

    cache_version1 = session.get(CacheVersion, waypoint1.document_id)
    cache_version2 = session.get(CacheVersion, waypoint2.document_id)
    cache_version3 = session.get(CacheVersion, waypoint3.document_id)
    cache_version_route = session.get(CacheVersion, route.document_id)
    cache_version_outing = session.get(CacheVersion, outing.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)

    assert cache_version1.version == 2
    assert cache_version2.version == 2
    assert cache_version3.version == 2
    assert cache_version_route.version == 2
    assert cache_version_outing.version == 2
    assert cache_version_untouched.version == 1


def test_update_cache_version_for_area(session):
    waypoint = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    area = Area()
    session.add_all([waypoint, waypoint_unrelated, area])
    session.flush()

    session.add(
        AreaAssociation(document_id=waypoint.document_id, area_id=area.document_id)
    )
    session.flush()

    update_cache_version_for_area(area)

    cache_version_waypoint = session.get(CacheVersion, waypoint.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)
    cache_version_area = session.get(CacheVersion, area.document_id)

    assert cache_version_waypoint.version == 2
    assert cache_version_untouched.version == 1
    # the cache key of the area is also not updated!
    assert cache_version_area.version == 1


def test_update_cache_version_for_map(session):
    waypoint = Waypoint(waypoint_type='summit')
    waypoint_unrelated = Waypoint(waypoint_type='summit')
    topo_map = TopoMap()
    session.add_all([waypoint, waypoint_unrelated, topo_map])
    session.flush()

    session.add(
        TopoMapAssociation(
            document_id=waypoint.document_id, topo_map_id=topo_map.document_id
        )
    )
    session.flush()

    update_cache_version_for_map(topo_map)

    cache_version_waypoint = session.get(CacheVersion, waypoint.document_id)
    cache_version_untouched = session.get(CacheVersion, waypoint_unrelated.document_id)
    cache_version_map = session.get(CacheVersion, topo_map.document_id)

    assert cache_version_waypoint.version == 2
    assert cache_version_untouched.version == 1
    # the cache key of the map is also not updated!
    assert cache_version_map.version == 1
