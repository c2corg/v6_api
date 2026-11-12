from dataclasses import dataclass

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


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    contributor: User
    contributor2: User
    route1: Route
    route2: Route
    route3: Route


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor = session.get(User, user_ids['contributor'])
    contributor2 = session.get(User, user_ids['contributor2'])

    route1 = Route(
        activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route1')]
    )
    session.add(route1)
    route2 = Route(
        activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route2')]
    )
    session.add(route2)
    route3 = Route(
        activities=['hiking'], locales=[RouteLocale(lang='en', title='Route3')]
    )
    session.add(route3)
    session.flush()

    session.add(
        DocumentTag(
            user_id=contributor2.id,
            document_id=route2.document_id,
            document_type=ROUTE_TYPE,
        )
    )
    session.flush()
    return Docs(
        contributor=contributor,
        contributor2=contributor2,
        route1=route1,
        route2=route2,
        route3=route3,
    )


class TestDocumentTagRest:
    PREFIX = '/tags/add'

    def test_tag_unauthenticated(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

    def test_tag(self, client, session, queue_config, docs):
        request_body = {'document_id': docs.route1.document_id}

        post_json_with_contributor(
            client, self.PREFIX, request_body, status=200, username='contributor'
        )

        assert has_tagged(docs.contributor.id, docs.route1.document_id)

        log = (
            session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == docs.route1.document_id)
            .filter(DocumentTagLog.user_id == docs.contributor.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert log.is_creation

        post_json_with_contributor(
            client, self.PREFIX, request_body, status=400, username='contributor'
        )

        assert_notified_es(queue_config)


class TestDocumentUntagRest:
    PREFIX = '/tags/remove'

    def test_untag_unauthenticated(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

    def test_untag(self, client, session, queue_config, docs):
        request_body = {'document_id': docs.route2.document_id}

        assert has_tagged(docs.contributor2.id, docs.route2.document_id)

        post_json_with_contributor(
            client, self.PREFIX, request_body, status=200, username='contributor2'
        )

        assert not has_tagged(docs.contributor2.id, docs.route2.document_id)

        post_json_with_contributor(
            client, self.PREFIX, request_body, status=400, username='contributor2'
        )

        log = (
            session.query(DocumentTagLog)
            .filter(DocumentTagLog.document_id == docs.route2.document_id)
            .filter(DocumentTagLog.user_id == docs.contributor2.id)
            .filter(DocumentTagLog.document_type == ROUTE_TYPE)
            .one()
        )
        assert not log.is_creation

        assert_notified_es(queue_config)

    def test_untag_not_tagged(self, client, queue_config, docs):
        request_body = {'document_id': docs.route1.document_id}

        assert not has_tagged(docs.contributor.id, docs.route1.document_id)

        post_json_with_contributor(
            client, self.PREFIX, request_body, status=400, username='contributor'
        )

        assert not has_tagged(docs.contributor.id, docs.route1.document_id)

        assert_not_notified_es(queue_config)


class TestDocumentTaggedRest:
    PREFIX = '/tags/has'

    def test_has_tagged_unauthenticated(self, client):
        client.get(self.PREFIX + '/123', status=403)

    def test_has_tagged(self, client, docs):
        headers = auth_headers(username='contributor2')
        response = client.get(
            f'{self.PREFIX}/{docs.route2.document_id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert body['todo']

    def test_has_tagged_not(self, client, docs):
        headers = auth_headers(username='contributor')
        response = client.get(
            f'{self.PREFIX}/{docs.route1.document_id}',
            status=200,
            headers=headers,
        )
        body = response.json

        assert not body['todo']
