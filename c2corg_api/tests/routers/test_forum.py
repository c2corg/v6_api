"""
Tests for the FastAPI forum router (``/v2/forum/topics``).

Mirrors ``c2corg_api/tests/views/test_forum.py``.
"""

from datetime import date
from unittest.mock import call, patch

from fastapi.testclient import TestClient
from requests.exceptions import ConnectionError

from c2corg_api.database import get_db
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.common.document_types import OUTING_TYPE
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.routers.forum import configure_forum_router
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app


class TestForumTopicRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_forum_router(settings)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def _add_test_data(self):
        self.waypoint = Waypoint(waypoint_type='summit', elevation=2203)
        self.locale_en = WaypointLocale(
            lang='en', title='Mont Granier', description='...', access='yep'
        )
        self.waypoint.locales.append(self.locale_en)
        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint)

        self.waypoint_with_topic = Waypoint(waypoint_type='summit', elevation=2203)
        document_topic = DocumentTopic(topic_id=1)
        self.locale_en_with_topic = WaypointLocale(
            lang='en',
            title='Mont Granier',
            description='...',
            access='yep',
            document_topic=document_topic,
        )
        self.waypoint_with_topic.locales.append(self.locale_en_with_topic)
        self.waypoint_with_topic.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)'
        )
        self.session.add(self.waypoint_with_topic)

        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'],
            height=1500,
            image_type='collaborative',
        )
        self.image_locale_en = DocumentLocale(lang='en', title='', description='')
        self.image.locales.append(self.image_locale_en)
        self.image.geometry = DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.image)

        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[OutingLocale(lang='en', title='Mont Granier / skitouring')],
        )
        self.session.add(self.outing)
        self.session.flush()

        for user_id in (global_userids['contributor'], global_userids['contributor2']):
            self.session.add(
                Association(
                    parent_document_id=user_id,
                    parent_document_type=USERPROFILE_TYPE,
                    child_document_id=self.outing.document_id,
                    child_document_type=OUTING_TYPE,
                )
            )

        self.session.flush()

    def test_post_unauthenticated(self):
        r = self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.waypoint.document_id, 'lang': 'en'},
        )
        assert r.status_code == 403

    def test_post_document_not_exists(self):
        r = self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.waypoint.document_id, 'lang': 'fr'},
            headers=self._auth_headers(),
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert 'Document not found' == errors[0]['description']

    def test_post_topic_exists(self):
        r = self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.waypoint_with_topic.document_id, 'lang': 'en'},
            headers=self._auth_headers(),
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert 'Topic already exists' == errors[0]['description']
        assert 1 == errors[0]['topic_id']

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient.create_post',
        side_effect=ConnectionError(),
    )
    def test_post_discourse_down(self, create_post_mock):
        r = self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.waypoint.document_id, 'lang': 'en'},
            headers=self._auth_headers(),
        )
        assert r.status_code == 500

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient.create_post',
        return_value={'topic_id': 10},
    )
    def test_post_success(self, create_post_mock):
        version = self.locale_en.version
        r = self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.waypoint.document_id, 'lang': 'en'},
            headers=self._auth_headers(),
        )
        assert r.status_code == 200
        json_body = r.json()

        self.session.expire(self.locale_en)
        assert 10 == self.locale_en.topic_id
        assert version == self.locale_en.version
        assert 10 == json_body.get('topic_id')

        cache_version = self.session.get(CacheVersion, self.waypoint.document_id)
        assert cache_version.version == 2

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient.create_post',
        return_value={'topic_id': 10},
    )
    def test_post_without_title(self, create_post_mock):
        """Test topic link content for documents without title"""
        locale = self.image_locale_en
        self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.image.document_id, 'lang': 'en'},
            headers=self._auth_headers(),
        )
        create_post_mock.assert_called_with(
            '<a href="https://www.camptocamp.org{}">{}</a>'.format(
                '/images/{}/{}'.format(locale.document_id, locale.lang),
                '/images/{}/{}'.format(locale.document_id, locale.lang),
            ),
            title='{}_{}'.format(locale.document_id, locale.lang),
            category='Commentaires',
        )

    @patch(
        'c2corg_api.security.discourse_client.DiscourseClient._post',
        side_effect=[{'topic_id': 10}, {}, {}],
    )
    def test_post_invite_participants(self, _post_mock):
        """Test outing participants are invited in the topic"""
        self.client.post(
            '/v2/forum/topics',
            json={'document_id': self.outing.document_id, 'lang': 'en'},
            headers=self._auth_headers(),
        )
        _post_mock.assert_has_calls(
            [
                call('/t/10/invite.json', user='contributor'),
                call('/t/10/invite.json', user='contributor2'),
            ],
            any_order=True,
        )
