import pytest
from sqlalchemy.sql.expression import and_

from c2corg_api.models.document import UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.tests import assert_errors_contain, auth_headers, send_json
from c2corg_api.views.document import create_new_version, update_version


class BaseMaskTest:
    @pytest.fixture(autouse=True)
    def _setup_base_mask_test(self, client, session, user_ids):

        self.contributor = session.get(User, user_ids['contributor'])
        contributor_id = user_ids['contributor']
        self.moderator = session.get(User, user_ids['moderator'])

        self.route = Route(
            activities=['skitouring'], locales=[RouteLocale(lang='en', title='Route')]
        )
        session.add(self.route)
        session.flush()

        create_new_version(self.route, contributor_id)
        session.flush()

        self.route.activities = ['skitouring', 'hiking']
        session.flush()

        update_version(
            self.route, contributor_id, 'new version', [UpdateType.FIGURES], []
        )
        session.flush()

    def mask(self, session, version_id):
        version = session.get(DocumentVersion, version_id)
        version.masked = True
        session.flush()

        assert self.is_masked(session, version_id)

    def is_masked(self, session, version_id):
        version = session.get(DocumentVersion, version_id)
        session.refresh(version)
        return version.masked

    def _get_first_version_params(self, session):
        document_id = self.route.document_id
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

    def _get_version(self, client, prefix, document_id, lang, version_id, user=None):
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


class TestVersionMaskRest(BaseMaskTest):
    @pytest.fixture(autouse=True)
    def _setup_test_version_mask_rest(self, client, _setup_base_mask_test):
        self._prefix = '/versions/mask'

    def test_mask_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_mask_invalid_document_id(self, client):
        request_body = {'document_id': -1, 'lang': 'en', 'version_id': 123456}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )

    def test_mask_invalid_version_id(self, client):
        document_id = self.route.document_id
        lang = 'en'
        version_id = 123456
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': version_id,
        }

        headers = auth_headers(username='moderator')
        response = send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )
        assert_errors_contain(
            response.json,
            'Bad Request',
            f'Unknown version {document_id}/{lang}/{version_id}',
        )

    def test_mask_latest_version(self, client, session):
        document_id = self.route.document_id
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
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )
        assert_errors_contain(
            response.json,
            'Bad Request',
            f'Version {document_id}/{lang}/{latest_version_id} is the latest one',
        )

    def test_mask(self, client, session):
        request_body = self._get_first_version_params(session)
        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        version_id = request_body['version_id']
        assert self.is_masked(session, version_id)

    def test_not_masked_version(self, client, session):
        request_body = self._get_first_version_params(session)
        document_id, lang, version_id = request_body.values()

        # anonymous
        body = self._get_version(client, 'routes', document_id, lang, version_id)
        assert not body['version']['masked']
        assert body['document']['activities'] == ['skitouring']

        # authenticated
        body = self._get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert not body['version']['masked']
        assert body['document'] is not None
        assert body['document']['activities'] == ['skitouring']

    def test_masked_version(self, client, session):
        request_body = self._get_first_version_params(session)
        document_id, lang, version_id = request_body.values()
        self.mask(session, version_id)

        # check masked version is referenced in the document history
        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        for version in body.json['versions']:
            assert version['masked'] == (version['version_id'] == version_id)

        # anonymous
        body = self._get_version(client, 'routes', document_id, lang, version_id)
        assert body['version']['masked']
        assert body['document'] is None

        # authenticated but not moderator
        body = self._get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert body['version']['masked']
        assert body['document'] is None

        # moderator
        body = self._get_version(
            client, 'routes', document_id, lang, version_id, 'moderator'
        )
        assert body['version']['masked']
        assert body['document'] is not None
        assert body['document']['activities'] == ['skitouring']

    def test_updated_cache(self, client, session):
        request_body = self._get_first_version_params(session)
        document_id, lang, version_id = request_body.values()

        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        assert not body.json['versions'][0]['masked']
        body = self._get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert not body['version']['masked']

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        body = client.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200
        )
        assert body.json['versions'][0]['masked']
        body = self._get_version(
            client, 'routes', document_id, lang, version_id, 'contributor'
        )
        assert body['version']['masked']


class TestVersionUnmaskRest(BaseMaskTest):
    @pytest.fixture(autouse=True)
    def _setup_test_version_unmask_rest(self, client, _setup_base_mask_test):
        self._prefix = '/versions/unmask'

    def test_unmask_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_unmask(self, client, session):
        request_body = self._get_first_version_params(session)
        document_id, lang, version_id = request_body.values()

        # first mask a version
        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', '/versions/mask', request_body, status=200, headers=headers
        )
        assert self.is_masked(session, version_id)

        # then check it's possible to unmask it
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )
        assert not self.is_masked(session, version_id)

        body = self._get_version(client, 'routes', document_id, lang, version_id)
        assert not body['version']['masked']
        assert body['document']['activities'] == ['skitouring']
