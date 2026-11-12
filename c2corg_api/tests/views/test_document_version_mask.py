from dataclasses import dataclass

import pytest
from sqlalchemy.sql.expression import and_

from c2corg_api.models.document import UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.tests import assert_errors_contain, auth_headers, send_json
from c2corg_api.views.document import create_new_version, update_version


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    contributor: User
    moderator: User
    route: Route


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor = session.get(User, user_ids['contributor'])
    contributor_id = user_ids['contributor']
    moderator = session.get(User, user_ids['moderator'])

    route = Route(
        activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route')]
    )
    session.add(route)
    session.flush()

    create_new_version(route, contributor_id)
    session.flush()

    route.activities = ['skitouring', 'hiking']
    session.flush()

    update_version(route, contributor_id, 'new version', [UpdateType.FIGURES], [])
    session.flush()
    return Docs(contributor=contributor, moderator=moderator, route=route)


def mask(session, version_id):
    version = session.get(DocumentVersion, version_id)
    version.masked = True
    session.flush()

    assert is_masked(session, version_id)


def is_masked(session, version_id):
    version = session.get(DocumentVersion, version_id)
    session.refresh(version)
    return version.masked


def _get_first_version_params(docs, session):
    document_id = docs.route.document_id
    lang = 'en'
    (first_version_id,) = (
        session.query(DocumentVersion.id)
        .filter(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.lang == lang,
            )
        )
        .order_by(DocumentVersion.id.asc())
        .first()
    )
    return {
        'document_id': document_id,
        'lang': lang,
        'version_id': first_version_id,
    }


def _get_version(client, prefix, document_id, lang, version_id, user=None):
    headers = {} if not user else auth_headers(username=user)
    response = client.get(
        f'/{prefix}/{document_id}/{lang}/{version_id}',
        headers=headers,
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    assert 'document' in body
    assert 'version' in body
    assert 'masked' in body['version']

    return body


class TestVersionMaskRest:
    PREFIX = '/versions/mask'

    def test_mask_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_mask_invalid_document_id(self, client):
        request_body = {'document_id': -1, 'lang': 'en', 'version_id': 123456}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )

    def test_mask_invalid_version_id(self, client, docs):
        document_id = docs.route.document_id
        lang = 'en'
        version_id = 123456
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': version_id,
        }

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )
        assert_errors_contain(
            response.json,
            'Bad Request',
            f'Unknown version {document_id}/{lang}/{version_id}',
        )

    def test_mask_latest_version(self, client, session, docs):
        document_id = docs.route.document_id
        lang = 'en'
        (latest_version_id,) = (
            session.query(DocumentVersion.id)
            .filter(
                and_(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.lang == lang,
                )
            )
            .order_by(DocumentVersion.id.desc())
            .first()
        )
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': latest_version_id,
        }

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )
        assert_errors_contain(
            response.json,
            'Bad Request',
            f'Version {document_id}/{lang}/{latest_version_id} is the latest one',
        )

    def test_mask(self, client, session, docs):
        request_body = _get_first_version_params(docs, session)
        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        version_id = request_body['version_id']
        assert is_masked(session, version_id)

    def test_not_masked_version(self, client, session, docs):
        request_body = _get_first_version_params(docs, session)
        document_id, lang, version_id = request_body.values()

        # anonymous
        body = _get_version(client, 'routes', document_id, lang, version_id)
        assert not body['version']['masked']
        assert body['document']['activities'] == ['skitouring']

        # authenticated
        body = _get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert not body['version']['masked']
        assert body['document'] is not None
        assert body['document']['activities'] == ['skitouring']

    def test_masked_version(self, client, session, docs):
        request_body = _get_first_version_params(docs, session)
        document_id, lang, version_id = request_body.values()
        mask(session, version_id)

        # check masked version is referenced in the document history
        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        for version in body.json['versions']:
            assert version['masked'] == (version['version_id'] == version_id)

        # anonymous
        body = _get_version(client, 'routes', document_id, lang, version_id)
        assert body['version']['masked']
        assert body['document'] is None

        # authenticated but not moderator
        body = _get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert body['version']['masked']
        assert body['document'] is None

        # moderator
        body = _get_version(
            client, 'routes', document_id, lang, version_id, 'moderator'
        )
        assert body['version']['masked']
        assert body['document'] is not None
        assert body['document']['activities'] == ['skitouring']

    def test_updated_cache(self, client, session, docs):
        request_body = _get_first_version_params(docs, session)
        document_id, lang, version_id = request_body.values()

        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        assert not body.json['versions'][0]['masked']
        body = _get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert not body['version']['masked']

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        assert body.json['versions'][0]['masked']
        body = _get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert body['version']['masked']


class TestVersionUnmaskRest:
    PREFIX = '/versions/unmask'

    def test_unmask_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_unmask(self, client, session, docs):
        request_body = _get_first_version_params(docs, session)
        document_id, lang, version_id = request_body.values()

        # first mask a version
        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', '/versions/mask', request_body, status=200, headers=headers
        )
        assert is_masked(session, version_id)

        # then check it's possible to unmask it
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )
        assert not is_masked(session, version_id)

        body = _get_version(client, 'routes', document_id, lang, version_id)
        assert not body['version']['masked']
        assert body['document']['activities'] == ['skitouring']
