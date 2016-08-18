from unittest.mock import patch

from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.tests.views import BaseTestRest

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.waypoint import Waypoint, WaypointLocale

from requests.exceptions import ConnectionError


class TestForumTopicRest(BaseTestRest):

    def _add_test_data(self):
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.locale_en = WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep')
        self.waypoint.locales.append(self.locale_en)
        self.waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.waypoint)

        self.waypoint_with_topic = Waypoint(
            waypoint_type='summit', elevation=2203)
        document_topic = DocumentTopic(topic_id=1)
        self.locale_en_with_topic = WaypointLocale(
            lang='en', title='Mont Granier', description='...',
            access='yep', document_topic=document_topic)
        self.waypoint_with_topic.locales.append(self.locale_en_with_topic)
        self.waypoint_with_topic.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.waypoint_with_topic)

        self.session.flush()

    def setUp(self):  # noqa
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_post_document_not_exists(self):
        json = self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.waypoint.document_id,
                'lang': 'fr'
            },
            status=400)
        errors = json.get('errors')
        self.assertEqual('Document not found', errors[0].get('description'))

    def test_post_topic_exists(self):
        json = self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.waypoint_with_topic.document_id,
                'lang': 'en'
            },
            status=400)
        errors = json.get('errors')
        self.assertEqual('Topic already exists', errors[0].get('description'))

    @patch('pydiscourse.client.DiscourseClient.create_post',
           side_effect=ConnectionError())
    def test_post_discourse_down(self, create_post_mock):
        self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.waypoint.document_id,
                'lang': 'en'
            },
            status=500)

    @patch('pydiscourse.client.DiscourseClient.create_post',
           return_value={"topic_id": 10})
    def test_post_success(self, create_post_mock):
        version = self.locale_en.version
        json = self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.waypoint.document_id,
                'lang': 'en'
            },
            status=200)
        self.session.expire(self.locale_en)
        self.assertEqual(10, self.locale_en.topic_id)
        self.assertEqual(version, self.locale_en.version)
        self.assertEqual(10, json.get('topic_id'))

        cache_version = self.session.query(CacheVersion).get(
            self.waypoint.document_id)
        self.assertEqual(cache_version.version, 2)
