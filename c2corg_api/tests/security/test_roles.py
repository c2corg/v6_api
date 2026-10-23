from unittest.mock import patch

from pyramid import testing
from pyramid.security import Authenticated

from c2corg_api.models import DBSession
from c2corg_api.security.roles import groupfinder
from c2corg_api.tests import BaseTestCase


class RolesTest(BaseTestCase):
    def test_groupfinder(self):
        self.assertEqual(
            [Authenticated], groupfinder(self.global_userids['contributor'], None)
        )
        self.assertEqual(
            ['group:moderators'], groupfinder(self.global_userids['moderator'], None)
        )

    def test_groupfinder_queries_once_per_request(self):
        request = testing.DummyRequest()
        moderator_id = self.global_userids['moderator']
        with patch.object(DBSession, 'query', wraps=DBSession.query) as query:
            for _ in range(3):
                self.assertEqual(
                    ['group:moderators'], groupfinder(moderator_id, request)
                )
        self.assertEqual(query.call_count, 1)

    def test_groupfinder_cache_is_per_user(self):
        request = testing.DummyRequest()
        self.assertEqual(
            ['group:moderators'],
            groupfinder(self.global_userids['moderator'], request),
        )
        self.assertEqual(
            [Authenticated], groupfinder(self.global_userids['contributor'], request)
        )

    def test_groupfinder_returns_a_copy(self):
        request = testing.DummyRequest()
        contributor_id = self.global_userids['contributor']
        groupfinder(contributor_id, request).append('group:moderators')
        self.assertEqual([Authenticated], groupfinder(contributor_id, request))
