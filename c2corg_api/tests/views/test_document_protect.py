from dataclasses import dataclass

import pytest

from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.views.document import create_new_version


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint: Waypoint
    locale: WaypointLocale
    waypoint2: Waypoint
    locale2: WaypointLocale


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor_id = user_ids['contributor']

    waypoint = Waypoint(waypoint_type='summit', elevation=2203)

    locale = WaypointLocale(lang='en', title='Mont Granier', description='...')
    waypoint.locales.append(locale)

    waypoint.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
    session.add(waypoint)
    session.flush()

    create_new_version(waypoint, contributor_id)

    waypoint2 = Waypoint(protected=True, waypoint_type='summit', elevation=2203)

    locale2 = WaypointLocale(lang='en', title='Mont Granier2', description='...')
    waypoint2.locales.append(locale2)

    waypoint2.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
    session.add(waypoint2)
    session.flush()

    create_new_version(waypoint2, contributor_id)

    session.flush()
    return Docs(waypoint=waypoint, locale=locale, waypoint2=waypoint2, locale2=locale2)


def is_protected(session, document_id):
    document = session.get(Document, document_id)
    session.refresh(document)
    return document.protected


class TestDocumentProtectRest:
    PREFIX = '/documents/protect'

    def test_protect_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_protect(self, client, session, docs):
        request_body = {'document_id': docs.waypoint.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_protected(session, docs.waypoint.document_id)

    def test_protect_already_protected_user(self, client, session, docs):
        """Test that protecting an already protected document
        does not raise an error.
        """
        request_body = {'document_id': docs.waypoint2.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert is_protected(session, docs.waypoint2.document_id)

    def test_protected_invalid_document_id(self, client):
        request_body = {'document_id': -1}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )


class TestDocumentUnprotectRest:
    PREFIX = '/documents/unprotect'

    def test_unprotect_unauthorized(self, client):
        send_json(client, 'post', self.PREFIX, {}, status=403)

        headers = auth_headers(username='contributor')
        send_json(client, 'post', self.PREFIX, {}, headers=headers, status=403)

    def test_unprotect(self, client, session, docs):
        request_body = {'document_id': docs.waypoint2.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert not is_protected(session, docs.waypoint2.document_id)

    def test_unprotect_already_unprotected_user(self, client, session, docs):
        """Test that unprotecting an already unprotected document
        does not raise an error.
        """
        request_body = {'document_id': docs.waypoint.document_id}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=200, headers=headers
        )

        assert not is_protected(session, docs.waypoint.document_id)

    def test_protected_invalid_document_id(self, client):
        request_body = {'document_id': -1}

        headers = auth_headers(username='moderator')
        send_json(
            client, 'post', self.PREFIX, request_body, status=400, headers=headers
        )
