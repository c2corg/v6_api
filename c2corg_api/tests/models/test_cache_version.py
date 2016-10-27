import datetime

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion, \
    update_cache_version, update_cache_version_associations, \
    update_cache_version_for_area, update_cache_version_for_map
from c2corg_api.models.outing import Outing, OUTING_TYPE
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE, WaypointLocale

from c2corg_api.tests import BaseTestCase
from c2corg_api.views.document import DocumentRest


class TestCacheVersion(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

    def test_trigger_create_cache_version(self):
        waypoint = Waypoint(waypoint_type='summit')
        self.session.add(waypoint)
        self.session.flush()

        cache_version = self.session.query(CacheVersion).get(
            waypoint.document_id)
        self.assertIsNotNone(cache_version)
        self.assertIsNotNone(cache_version.version)
        self.assertIsNotNone(cache_version.last_updated)

    def test_update_cache_version_single_wp(self):
        waypoint = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        self.session.add_all([waypoint, waypoint_unrelated])
        self.session.flush()

        cache_version = self.session.query(CacheVersion).get(
            waypoint.document_id)
        cache_version.last_updated = datetime.datetime(2016, 1, 1, 12, 1, 0)
        self.session.flush()
        current_version = cache_version.version
        current_last_updated = cache_version.last_updated

        update_cache_version(waypoint)
        self.session.refresh(cache_version)
        self.assertEqual(cache_version.version, current_version + 1)
        self.assertNotEqual(cache_version.last_updated, current_last_updated)

        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_wp_with_associations(self):
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint3 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        self.session.add_all(
            [waypoint1, waypoint2, waypoint3, waypoint_unrelated])
        self.session.flush()

        self.session.add(Association.create(waypoint1, waypoint2))
        self.session.add(Association.create(waypoint3, waypoint1))
        self.session.flush()

        update_cache_version(waypoint1)
        cache_version1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version2 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version3 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version1.version, 2)
        self.assertEqual(cache_version2.version, 2)
        self.assertEqual(cache_version3.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_wp_as_main_wp(self):
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint3 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        route = Route(main_waypoint=waypoint1, activities=['skitouring'])
        self.session.add_all(
            [waypoint1, waypoint2, waypoint3, waypoint_unrelated, route])
        self.session.flush()

        self.session.add(Association.create(waypoint1, route))
        self.session.add(Association.create(waypoint2, route))
        self.session.add(Association.create(waypoint3, waypoint2))
        self.session.flush()

        update_cache_version(waypoint1)
        cache_version_wp1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version_wp2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version_wp3 = self.session.query(CacheVersion).get(
            waypoint3.document_id)
        cache_version_route = self.session.query(CacheVersion).get(
            route.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version_wp1.version, 3)
        self.assertEqual(cache_version_wp2.version, 2)
        self.assertEqual(cache_version_wp3.version, 2)
        self.assertEqual(cache_version_route.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_route(self):
        route1 = Route(activities=['skitouring'])
        route2 = Route(activities=['skitouring'])
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        self.session.add_all(
            [waypoint1, waypoint2, waypoint_unrelated, route1, route2])
        self.session.flush()

        self.session.add(Association.create(waypoint1, route1))
        self.session.add(Association.create(route2, route1))
        self.session.add(Association.create(waypoint2, waypoint1))
        self.session.flush()

        update_cache_version(route1)
        cache_version_route1 = self.session.query(CacheVersion).get(
            route1.document_id)
        cache_version_route2 = self.session.query(CacheVersion).get(
            route2.document_id)
        cache_version_wp1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version_wp2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version_route1.version, 2)
        self.assertEqual(cache_version_route2.version, 2)
        self.assertEqual(cache_version_wp1.version, 3)
        self.assertEqual(cache_version_wp2.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_outing(self):
        outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 2, 1))
        route1 = Route(activities=['skitouring'])
        route2 = Route(activities=['skitouring'])
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        self.session.add_all(
            [outing, waypoint1, waypoint2, waypoint_unrelated, route1, route2])
        self.session.flush()

        self.session.add(Association.create(route1, outing))
        self.session.add(Association.create(waypoint1, route1))
        self.session.add(Association.create(route2, outing))
        self.session.add(Association.create(waypoint2, waypoint1))
        self.session.flush()

        update_cache_version(outing)
        cache_version_outing = self.session.query(CacheVersion).get(
            outing.document_id)
        cache_version_route1 = self.session.query(CacheVersion).get(
            route1.document_id)
        cache_version_route2 = self.session.query(CacheVersion).get(
            route2.document_id)
        cache_version_wp1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version_wp2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version_outing.version, 2)
        self.assertEqual(cache_version_route1.version, 2)
        self.assertEqual(cache_version_route2.version, 2)
        self.assertEqual(cache_version_wp1.version, 2)
        self.assertEqual(cache_version_wp2.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_user(self):
        """ Test that outings are invalidated if an user name changes.
        """
        outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 2, 1))
        user_profile = UserProfile()
        self.session.add_all([outing, user_profile])
        self.session.flush()

        self.session.add(Association.create(user_profile, outing))
        self.session.flush()

        update_cache_version(user_profile)
        cache_version_user_profile = self.session.query(CacheVersion).get(
            user_profile.document_id)
        cache_version_outing = self.session.query(CacheVersion).get(
            outing.document_id)

        self.assertEqual(cache_version_outing.version, 2)
        self.assertEqual(cache_version_user_profile.version, 2)

    def test_update_cache_version_user_document_version(self):
        """ Test that a document is invalidated if a user name of a user that
         edited one of the document versions is changed.
        """
        waypoint = Waypoint(
            waypoint_type='summit', elevation=2203, locales=[
                WaypointLocale(lang='en', title='...', description='...')])

        user_profile = UserProfile()
        user = User(
            name='test_user',
            username='test_user', email='test_user@camptocamp.org',
            forum_username='testuser', password='test_user',
            email_validated=True, profile=user_profile)
        self.session.add_all([waypoint, user_profile, user])
        self.session.flush()

        DocumentRest.create_new_version(waypoint, user.id)

        update_cache_version(user_profile)
        cache_version_user_profile = self.session.query(CacheVersion).get(
            user_profile.document_id)
        cache_version_waypoint = self.session.query(CacheVersion).get(
            waypoint.document_id)

        self.assertEqual(cache_version_waypoint.version, 2)
        self.assertEqual(cache_version_user_profile.version, 2)

    def test_update_cache_version_associations_removed_wp(self):
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint3 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        self.session.add_all(
            [waypoint1, waypoint2, waypoint3, waypoint_unrelated])
        self.session.flush()

        update_cache_version_associations([], [
            {'parent_id': waypoint1.document_id, 'parent_type': WAYPOINT_TYPE,
             'child_id': waypoint2.document_id, 'child_type': WAYPOINT_TYPE},
            {'parent_id': waypoint3.document_id, 'parent_type': WAYPOINT_TYPE,
             'child_id': waypoint1.document_id, 'child_type': WAYPOINT_TYPE}
        ])

        cache_version1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version3 = self.session.query(CacheVersion).get(
            waypoint3.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version1.version, 2)
        self.assertEqual(cache_version2.version, 2)
        self.assertEqual(cache_version3.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_associations_removed_wp_route(self):
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint3 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        route = Route(activities=['skitouring'])
        self.session.add_all(
            [waypoint1, waypoint2, waypoint3, waypoint_unrelated, route])
        self.session.flush()

        self.session.add(Association.create(waypoint2, waypoint1))
        self.session.add(Association.create(waypoint3, waypoint2))
        self.session.flush()

        update_cache_version_associations([], [
            {'parent_id': waypoint1.document_id, 'parent_type': WAYPOINT_TYPE,
             'child_id': route.document_id, 'child_type': ROUTE_TYPE}
        ])

        cache_version1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version3 = self.session.query(CacheVersion).get(
            waypoint3.document_id)
        cache_version_route = self.session.query(CacheVersion).get(
            route.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version1.version, 2)
        self.assertEqual(cache_version2.version, 2)
        self.assertEqual(cache_version3.version, 2)
        self.assertEqual(cache_version_route.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_associations_removed_route_outing(self):
        waypoint1 = Waypoint(waypoint_type='summit')
        waypoint2 = Waypoint(waypoint_type='summit')
        waypoint3 = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        route = Route(activities=['skitouring'])
        outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 2, 1))
        self.session.add_all(
            [waypoint1, waypoint2, waypoint3, waypoint_unrelated,
             route, outing])
        self.session.flush()

        self.session.add(Association.create(waypoint1, route))
        self.session.add(Association.create(waypoint2, waypoint1))
        self.session.add(Association.create(waypoint3, waypoint2))
        self.session.flush()

        update_cache_version_associations([], [
            {'parent_id': route.document_id, 'parent_type': ROUTE_TYPE,
             'child_id': outing.document_id, 'child_type': OUTING_TYPE}
        ])

        cache_version1 = self.session.query(CacheVersion).get(
            waypoint1.document_id)
        cache_version2 = self.session.query(CacheVersion).get(
            waypoint2.document_id)
        cache_version3 = self.session.query(CacheVersion).get(
            waypoint3.document_id)
        cache_version_route = self.session.query(CacheVersion).get(
            route.document_id)
        cache_version_outing = self.session.query(CacheVersion).get(
            outing.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)

        self.assertEqual(cache_version1.version, 2)
        self.assertEqual(cache_version2.version, 2)
        self.assertEqual(cache_version3.version, 2)
        self.assertEqual(cache_version_route.version, 2)
        self.assertEqual(cache_version_outing.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)

    def test_update_cache_version_for_area(self):
        waypoint = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        area = Area()
        self.session.add_all([waypoint, waypoint_unrelated, area])
        self.session.flush()

        self.session.add(AreaAssociation(
            document_id=waypoint.document_id, area_id=area.document_id))
        self.session.flush()

        update_cache_version_for_area(area)

        cache_version_waypoint = self.session.query(CacheVersion).get(
            waypoint.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)
        cache_version_area = self.session.query(CacheVersion).get(
            area.document_id)

        self.assertEqual(cache_version_waypoint.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)
        # the cache key of the area is also not updated!
        self.assertEqual(cache_version_area.version, 1)

    def test_update_cache_version_for_map(self):
        waypoint = Waypoint(waypoint_type='summit')
        waypoint_unrelated = Waypoint(waypoint_type='summit')
        topo_map = TopoMap()
        self.session.add_all([waypoint, waypoint_unrelated, topo_map])
        self.session.flush()

        self.session.add(TopoMapAssociation(
            document_id=waypoint.document_id,
            topo_map_id=topo_map.document_id))
        self.session.flush()

        update_cache_version_for_map(topo_map)

        cache_version_waypoint = self.session.query(CacheVersion).get(
            waypoint.document_id)
        cache_version_untouched = self.session.query(CacheVersion).get(
            waypoint_unrelated.document_id)
        cache_version_map = self.session.query(CacheVersion).get(
            topo_map.document_id)

        self.assertEqual(cache_version_waypoint.version, 2)
        self.assertEqual(cache_version_untouched.version, 1)
        # the cache key of the map is also not updated!
        self.assertEqual(cache_version_map.version, 1)
