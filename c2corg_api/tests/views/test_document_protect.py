import pytest

from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.views.document import create_new_version


class BaseProtectTest:
    @pytest.fixture(autouse=True)
    def _setup_base_protect_test(self, client, session, user_ids):
        contributor_id = user_ids['contributor']

        self.waypoint = Waypoint(waypoint_type='summit', elevation=2203)

        self.locale = WaypointLocale(lang='en', title='Mont Granier', description='...')
        self.waypoint.locales.append(self.locale)

        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        session.add(self.waypoint)
        session.flush()

        create_new_version(self.waypoint, contributor_id)

        self.waypoint2 = Waypoint(
            protected=True, waypoint_type='summit', elevation=2203
        )

        self.locale2 = WaypointLocale(
            lang='en', title='Mont Granier2', description='...'
        )
        self.waypoint2.locales.append(self.locale2)

        self.waypoint2.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        session.add(self.waypoint2)
        session.flush()

        create_new_version(self.waypoint2, contributor_id)

        session.flush()

    def is_protected(self, session, document_id):
        document = session.get(Document, document_id)
        session.refresh(document)
        return document.protected


class TestDocumentProtectRest(BaseProtectTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_protect_rest(self, client, _setup_base_protect_test):
        self._prefix = '/documents/protect'

    def test_protect_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_protect(self, client, session):
        request_body = {'document_id': self.waypoint.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_protected(session, self.waypoint.document_id)

    def test_protect_already_protected_user(self, client, session):
        """Test that protecting an already protected document
        does not raise an error.
        """
        request_body = {'document_id': self.waypoint2.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert self.is_protected(session, self.waypoint2.document_id)

    def test_protected_invalid_document_id(self, client):
        request_body = {'document_id': -1}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )


class TestDocumentUnprotectRest(BaseProtectTest):
    @pytest.fixture(autouse=True)
    def _setup_test_document_unprotect_rest(self, client, _setup_base_protect_test):
        self._prefix = '/documents/unprotect'

    def test_unprotect_unauthorized(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self._prefix, {}, headers=headers, status=403)

    def test_unprotect(self, client, session):
        request_body = {'document_id': self.waypoint2.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert not self.is_protected(session, self.waypoint2.document_id)

    def test_unprotect_already_unprotected_user(self, client, session):
        """Test that unprotecting an already unprotected document
        does not raise an error.
        """
        request_body = {'document_id': self.waypoint.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        assert not self.is_protected(session, self.waypoint.document_id)

    def test_protected_invalid_document_id(self, client):
        request_body = {'document_id': -1}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self._prefix, request_body, status=400, headers=headers
        )
