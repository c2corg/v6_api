from c2corg_api.models.route import Route, RouteLocale, ROUTE_TYPE
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document_tag import get_tag_relation


def has_tagged(user_id, document_id):
    return get_tag_relation(user_id, document_id) is not None


class BaseDocumentTagTest(BaseTestRest):

    def setUp(self):  # noqa
        super().setUp()

        self.contributor = self.session.query(User).get(
            self.global_userids['contributor'])
        self.contributor2 = self.session.query(User).get(
            self.global_userids['contributor2'])

        self.route1 = Route(activities=['skitouring'], locales=[
            RouteLocale(lang='en', title='Route1')
        ])
        self.session.add(self.route1)
        self.route2 = Route(activities=['skitouring'], locales=[
            RouteLocale(lang='en', title='Route2')
        ])
        self.session.add(self.route2)
        self.route3 = Route(activities=['hiking'], locales=[
            RouteLocale(lang='en', title='Route3')
        ])
        self.session.add(self.route3)
        self.session.flush()

        self.session.add(DocumentTag(
            user_id=self.contributor2.id,
            document_id=self.route2.document_id,
            document_type=ROUTE_TYPE))
        self.session.flush()


class TestDocumentTagRest(BaseDocumentTagTest):

    def setUp(self):  # noqa
        super().setUp()
        self._prefix = '/tags/add'

    def test_tag_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_tag(self):
        request_body = {
            'document_id': self.route1.document_id
        }

        self.post_json_with_contributor(
            self._prefix, request_body, status=200, username='contributor')

        self.assertTrue(
            has_tagged(self.contributor.id, self.route1.document_id))

        log = self.session.query(DocumentTagLog). \
            filter(DocumentTagLog.document_id == self.route1.document_id). \
            filter(DocumentTagLog.user_id == self.contributor.id). \
            filter(DocumentTagLog.document_type == ROUTE_TYPE). \
            one()
        self.assertTrue(log.is_creation)

        self.post_json_with_contributor(
            self._prefix, request_body, status=400, username='contributor')

        self.assertNotifiedEs()


class TestDocumentUntagRest(BaseDocumentTagTest):

    def setUp(self):  # noqa
        super().setUp()
        self._prefix = '/tags/remove'

    def test_untag_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_untag(self):
        request_body = {
            'document_id': self.route2.document_id
        }

        self.assertTrue(
            has_tagged(self.contributor2.id, self.route2.document_id))

        self.post_json_with_contributor(
            self._prefix, request_body, status=200, username='contributor2')

        self.assertFalse(
            has_tagged(self.contributor2.id, self.route2.document_id))

        self.post_json_with_contributor(
            self._prefix, request_body, status=400, username='contributor2')

        log = self.session.query(DocumentTagLog). \
            filter(DocumentTagLog.document_id == self.route2.document_id). \
            filter(DocumentTagLog.user_id == self.contributor2.id). \
            filter(DocumentTagLog.document_type == ROUTE_TYPE). \
            one()
        self.assertFalse(log.is_creation)

        self.assertNotifiedEs()

    def test_untag_not_tagged(self):
        request_body = {
            'document_id': self.route1.document_id
        }

        self.assertFalse(
            has_tagged(self.contributor.id, self.route1.document_id))

        self.post_json_with_contributor(
            self._prefix, request_body, status=400, username='contributor')

        self.assertFalse(
            has_tagged(self.contributor.id, self.route1.document_id))

        self.assertNotNotifiedEs()


class TestDocumentTaggedRest(BaseDocumentTagTest):

    def setUp(self):  # noqa
        super().setUp()
        self._prefix = '/tags/has'

    def test_has_tagged_unauthenticated(self):
        self.app.get(self._prefix + '/123', status=403)

    def test_has_tagged(self):
        headers = self.add_authorization_header(username='contributor2')
        response = self.app.get(
            '{}/{}'.format(self._prefix, self.route2.document_id),
            status=200, headers=headers)
        body = response.json

        self.assertTrue(body['todo'])

    def test_has_tagged_not(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(
            '{}/{}'.format(self._prefix, self.route1.document_id),
            status=200, headers=headers)
        body = response.json

        self.assertFalse(body['todo'])
