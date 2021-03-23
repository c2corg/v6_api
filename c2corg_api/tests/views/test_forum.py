import datetime
from unittest.mock import patch, call

from c2corg_api.models.common.document_types import OUTING_TYPE

from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.tests.views import BaseTestRest

from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.image import Image

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

        self.image = Image(
            filename='image.jpg',
            activities=['paragliding'], height=1500,
            image_type='collaborative')
        self.image_locale_en = DocumentLocale(
            lang='en', title='', description='')
        self.image.locales.append(self.image_locale_en)
        self.image.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956 5723604)')
        self.session.add(self.image)

        self.outing = Outing(
            activities=['skitouring'],
            date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            locales=[OutingLocale(lang='en',
                                  title='Mont Granier / skitouring')]
        )
        self.session.add(self.outing)
        self.session.flush()

        for user_id in (
            self.global_userids['contributor'],
            self.global_userids['contributor2']
        ):
            self.session.add(Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing.document_id,
                child_document_type=OUTING_TYPE))

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
        self.assertEqual(1, errors[0].get('topic_id'))

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

    @patch('pydiscourse.client.DiscourseClient.create_post',
           return_value={"topic_id": 10})
    def test_post_without_title(self, create_post_mock):
        """Test topic link content for documents without title"""
        locale = self.image_locale_en
        referer = ('https://www.camptocamp.org/images/{}/{}'
                   .format(locale.document_id,
                           locale.lang))
        self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.image.document_id,
                'lang': 'en'
            },
            headers={
                'Referer': referer
            },
            status=200)
        create_post_mock.assert_called_with(
            '<a href="{}">{}</a>'.format(
                referer,
                "/images/{}/{}".format(locale.document_id, locale.lang)),
            title='{}_{}'.format(locale.document_id, locale.lang),
            category='Commentaires')

    @patch('pydiscourse.client.DiscourseClient._post',
           side_effect=[{"topic_id": 10},
                        {},
                        {}])
    def test_post_invite_participants(self, _post_mock):
        """Test outing participants are invited in the topic"""
        self.post_json_with_contributor(
            '/forum/topics',
            {
                'document_id': self.outing.document_id,
                'lang': 'en'
            },
            status=200)
        _post_mock.assert_has_calls(
            [
                call('/t/10/invite.json', user='contributor'),
                call('/t/10/invite.json', user='contributor2')],
            any_order=True)
