from c2corg_api.models.area import Area
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE

from c2corg_api.tests import BaseTestCase


class TestDocumentChange(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self.user1 = self.session.query(User).get(
            self.global_userids['contributor'])
        self.user2 = self.session.query(User).get(
            self.global_userids['contributor2'])
        self.waypoint = Waypoint(waypoint_type='summit')
        self.session.add(self.waypoint)
        self.area1 = Area(area_type='range')
        self.area2 = Area(area_type='range')
        self.session.add_all([self.waypoint, self.area1, self.area2])
        self.session.flush()

    def test_check_user_and_area_ids_on_create_valid(self):
        users_ids = [self.user1.id, self.user2.id]
        area_ids = [self.area1.document_id, self.area2.document_id]
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=area_ids, user_ids=users_ids
        )
        self.session.add(change)
        self.session.flush()
        # no error, ok

    def test_check_user_ids_on_create_invalid(self):
        """try to create a "change" with an invalid user id
        """
        users_ids = [self.user1.id, -12345678]
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=[], user_ids=users_ids
        )
        try:
            self.session.add(change)
            self.session.flush()
        except Exception as exc:
            self.assertTrue('Invalid user id: -12345678' in exc.orig.pgerror)
        else:
            self.fail('invalid user id not detected')

    def test_check_area_ids_on_create_invalid(self):
        """try to create a "change" with an invalid area id
        """
        area_ids = [self.area1.document_id, -123456]
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=area_ids, user_ids=[]
        )
        try:
            self.session.add(change)
            self.session.flush()
        except Exception as exc:
            self.assertTrue('Invalid area id: -123456' in exc.orig.pgerror)
        else:
            self.fail('invalid area id not detected')

    def test_check_user_ids_on_update_invalid(self):
        """try to update a "change" with an invalid user id
        """
        # first create the change without user ids
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=[], user_ids=[]
        )
        self.session.add(change)
        self.session.flush()

        # then set the user ids and save
        users_ids = [self.user1.id, -12345678]
        change.user_ids = users_ids
        try:
            self.session.flush()
        except Exception as exc:
            self.assertTrue('Invalid user id: -12345678' in exc.orig.pgerror)
        else:
            self.fail('invalid user id not detected')

    def test_check_changes_on_user_deletion_ok(self):
        """try to delete a user that is not referenced in a "change"
        """
        user = User(
            name='test',
            username='test', email='test@camptocamp.org',
            forum_username='test',
            moderator=True, password='...', email_validated=True,
            profile=UserProfile(categories=['amateur'])
        )
        self.session.add(user)
        self.session.flush()
        self.session.delete(user)
        self.session.flush()
        # no error, ok

    def test_check_changes_on_user_deletion_error(self):
        """try to delete a user that is still referenced in a "change"
        """
        user = User(
            name='test',
            username='test', email='test@camptocamp.org',
            forum_username='test',
            moderator=True, password='...', email_validated=True,
            profile=UserProfile(categories=['amateur'])
        )
        self.session.add(user)
        self.session.flush()

        user_ids = [user.id]
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=[], user_ids=user_ids
        )
        self.session.add(change)
        self.session.flush()

        try:
            self.session.delete(user)
            self.session.flush()
        except Exception as exc:
            self.assertTrue('still references user id' in exc.orig.pgerror)
        else:
            self.fail('user is still referenced in change')

    def test_check_changes_on_area_deletion_ok(self):
        """try to delete an area that is not referenced in a "change"
        """
        self.session.query(CacheVersion). \
            filter(CacheVersion.document_id == self.area1.document_id). \
            delete()
        self.session.delete(self.area1)
        self.session.flush()
        # no error, ok

    def test_check_changes_on_area_deletion_error(self):
        """try to delete an area that is still referenced in a "change"
        """
        area_ids = [self.area1.document_id]
        change = DocumentChange(
            user=self.user1, change_type='created', document=self.waypoint,
            document_type=WAYPOINT_TYPE, area_ids=area_ids, user_ids=[]
        )
        self.session.add(change)
        self.session.flush()

        try:
            self.session.query(CacheVersion). \
                filter(CacheVersion.document_id == self.area1.document_id). \
                delete()
            self.session.delete(self.area1)
            self.session.flush()
        except Exception as exc:
            self.assertTrue('still references area id' in exc.orig.pgerror)
        else:
            self.fail('area is still referenced in change')
