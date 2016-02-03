from c2corg_api.security.roles import groupfinder
from c2corg_api.tests import BaseTestCase
from pyramid.security import Authenticated


class RolesTest(BaseTestCase):

    def test_groupfinder(self):
        self.assertEqual(
            [Authenticated],
            groupfinder(self.global_userids['contributor'], None)
        )
        self.assertEqual(
            ['group:moderators'],
            groupfinder(self.global_userids['moderator'], None)
        )
