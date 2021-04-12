from c2corg_api.models.user import User
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.models.common.attributes import mailinglists


class TestUserMailinglistsRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestUserMailinglistsRest, self).setUp()
        self._prefix = '/users/mailinglists'

        self.contributor = self.session.query(User).get(
            self.global_userids['contributor'])
        ml1 = Mailinglist(
            listname='meteofrance-74',
            email=self.contributor.email,
            user_id=self.contributor.id,
            user=self.contributor
        )
        ml2 = Mailinglist(
            listname='avalanche.en',
            email=self.contributor.email,
            user_id=self.contributor.id,
            user=self.contributor
        )
        self.session.add_all([ml1, ml2])
        self.session.flush()

    def test_get_mailinglists_unauthenticated(self):
        self.app.get(self._prefix, status=403)

    def test_get_mailinglists(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(self._prefix, status=200, headers=headers)
        body = response.json

        self.assertEqual(len(body), len(mailinglists))
        for ml in mailinglists:
            self.assertIn(ml, body)
            if ml in ['meteofrance-74', 'avalanche.en']:
                self.assertTrue(body[ml])
            else:
                self.assertFalse(body[ml])

    def test_post_mailinglists_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_post_mailinglists_invalid(self):
        request_body = {
            'wrong_mailinglist_name': True,
            'avalanche': 'incorrect_value'
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertIsNotNone(self.get_error(errors, 'wrong_mailinglist_name'))
        self.assertIsNotNone(self.get_error(errors, 'avalanche'))

    def test_post_mailinglists(self):
        request_body = {
            'meteofrance-66': True,
            'meteofrance-74': False
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        mls = self.session.query(Mailinglist.listname).filter(
            Mailinglist.email == self.contributor.email).all()
        subscribed_mailinglists = [list[0] for list in mls]
        self.assertEqual(len(subscribed_mailinglists), 2)
        self.assertIn('meteofrance-66', subscribed_mailinglists)
        self.assertIn('avalanche.en', subscribed_mailinglists)
        self.assertNotIn('meteofrance-74', subscribed_mailinglists)
