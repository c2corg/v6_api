import pytest

from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.tests import (
    assert_not_notified_es,
    assert_notified_es,
    auth_headers,
    post_json_with_contributor,
    send_json,
)
from c2corg_api.views.document_tag import get_tag_relation


def has_tagged(user_id, document_id):
    return get_tag_relation(user_id, document_id) is not None


class BaseDocumentTagTest:
    @pytest.fixture(autouse=True)
    def _setup_base_document_tag_test(self, client, session, user_ids):

        self.contributor = session.get(User, user_ids['contributor'])
        self.contributor2 = session.get(User, user_ids['contributor2'])

        self.route1 = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route1')]
        )
        session.add(self.route1)
        self.route2 = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route2')]
        )
        session.add(self.route2)
        self.route3 = Route(
            activities=['hiking'], locales=[RouteLocale(lang='en', title='Route3')]
        )
        session.add(self.route3)
        session.flush()

        session.add(
            DocumentTag(
                user_id=self.contributor2.id,
                document_id=self.route2.document_id,
                document_type=ROUTE_TYPE,
            )
        )
        session.flush()


class TestDocumentTagRest(BaseDocumentTagTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_tag_rest(self, client, _setup_base_document_tag_test):
        self._prefix = '/tags/add'

    def test_tag_unauthenticated(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

    def test_tag(self, client, session, queue_config):
        request_body = {'document_id': self.route1.document_id}

        post_json_with_contributor(
            client, self._prefix, request_body, status=200, username='contributor'
        )

        assert has_tagged(self.contributor.id, self.route1.document_id)

        log = (
            session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == self.route1.document_id)
            .filter(DocumentTagLog.user_id == self.contributor.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert log.is_creation

        post_json_with_contributor(
            client, self._prefix, request_body, status=400, username='contributor'
        )

        assert_notified_es(queue_config)


class TestDocumentUntagRest(BaseDocumentTagTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_untag_rest(self, client, _setup_base_document_tag_test):
        self._prefix = '/tags/remove'

    def test_untag_unauthenticated(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

    def test_untag(self, client, session, queue_config):
        request_body = {'document_id': self.route2.document_id}

        assert has_tagged(self.contributor2.id, self.route2.document_id)

        post_json_with_contributor(
            client, self._prefix, request_body, status=200, username='contributor2'
        )

        assert not has_tagged(self.contributor2.id, self.route2.document_id)

        post_json_with_contributor(
            client, self._prefix, request_body, status=400, username='contributor2'
        )

        log = (
            session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == self.route2.document_id)
            .filter(DocumentTagLog.user_id == self.contributor2.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert not log.is_creation

        assert_notified_es(queue_config)

    def test_untag_not_tagged(self, client, queue_config):
        request_body = {'document_id': self.route1.document_id}

        assert not has_tagged(self.contributor.id, self.route1.document_id)

        post_json_with_contributor(
            client, self._prefix, request_body, status=400, username='contributor'
        )

        assert not has_tagged(self.contributor.id, self.route1.document_id)

        assert_not_notified_es(queue_config)


class TestDocumentTaggedRest(BaseDocumentTagTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_tagged_rest(self, client, _setup_base_document_tag_test):
        self._prefix = '/tags/has'

    def test_has_tagged_unauthenticated(self, client):
        client.get(self._prefix + '/123', status=403)

    def test_has_tagged(self, client):
        headers = auth_headers(username='contributor2')
        response = client.get(
            f'{self._prefix}/{self.route2.document_id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['todo']

    def test_has_tagged_not(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(
            f'{self._prefix}/{self.route1.document_id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert not body['todo']
