import datetime
from unittest.mock import patch

from c2corg_api.models import es_sync
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.sync import get_changed_documents, \
    get_documents_per_type,  sync_documents, create_search_documents
from c2corg_api.tests import BaseTestCase, global_userids
from c2corg_api.views.document import DocumentRest


class SyncTest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_get_changed_documents(self):
        last_update, _ = es_sync.get_status(self.session)

        changed_documents = get_changed_documents(self.session, last_update)
        self.assertEqual(len(changed_documents), 4)
        self.assertEqual('r', changed_documents[0][1])
        self.assertEqual('w', changed_documents[1][1])

        self.assertEqual(
            len(get_changed_documents(
                self.session, last_update + datetime.timedelta(0, 1))),
            0)

    def test_get_documents_per_type(self):
        changed_documents = [(1, 'r'), (2, 'w'), (3, 'r'), (4, 'r'), (4, 'r')]
        docs_per_type = get_documents_per_type(changed_documents)
        self.assertEqual(docs_per_type, {'r': {1, 3, 4}, 'w': {2}})

    def test_create_search_documents(self):
        search_documents = []
        batch_mock = self._create_mock_match(search_documents)(None, 1000)

        self.route1.geometry = DocumentGeometry()
        self.route1.geometry.lon_lat = \
            '{"type": "Point", "coordinates": [6, 46]}'
        create_search_documents('r', [self.route1], batch_mock)
        doc = search_documents[0]

        self.assertEqual(doc['_op_type'], 'index')
        self.assertEqual(doc['_id'], self.route1.document_id)
        self.assertEqual(doc['title_en'], 'Mont Blanc : Face N')
        self.assertEqual(doc['description_en'], '...')
        self.assertEqual(doc['geom'], [6, 46])

    def test_create_search_documents_user_profile(self):
        search_documents = []
        batch_mock = self._create_mock_match(search_documents)(None, 1000)

        document_id = global_userids['contributor']
        user_profile = self.session.query(UserProfile).get(document_id)

        create_search_documents('u', [user_profile], batch_mock)
        doc = search_documents[0]

        self.assertEqual(doc['_op_type'], 'index')
        self.assertEqual(doc['_id'], document_id)
        self.assertEqual(doc['title_en'], 'contributor Contributor')
        self.assertEqual(doc['description_en'], 'Me')
        self.assertEqual(doc['title_fr'], 'contributor Contributor')
        self.assertEqual(doc['description_fr'], 'Moi')

    @patch('c2corg_api.scripts.es.sync.ElasticBatch')
    def test_sync_documents(self, mock):
        search_documents = []
        mock.side_effect = self._create_mock_match(search_documents)

        changed_documents = [
            (self.waypoint1.document_id, 'w'),
            (self.waypoint2.document_id, 'w'),
            (self.waypoint3.document_id, 'w'),
            (self.route1.document_id, 'r')]
        sync_documents(self.session, changed_documents)
        self.assertEqual(len(search_documents), 4)

        redirected_doc = next(
            filter(
                lambda doc: doc['_id'] == self.waypoint3.document_id,
                search_documents),
            None)
        self.assertEqual(redirected_doc['_op_type'], 'delete')

        waypoint1_doc = next(
            filter(
                lambda doc: doc['_id'] == self.waypoint1.document_id,
                search_documents),
            None)
        self.assertAlmostEqual(waypoint1_doc['geom'][0], 5.71288995)
        self.assertAlmostEqual(waypoint1_doc['geom'][1], 45.64476395)

    def _create_mock_match(self, actions):
        class MockBatch(object):
            def __init__(self, client, batch_size):
                pass

            def add(self, action):
                actions.append(action)

            def __enter__(self):
                pass

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        return MockBatch

    def _add_test_data(self):
        _, date_now = es_sync.get_status(self.session)
        es_sync.mark_as_updated(self.session, date_now)

        self.waypoint1 = Waypoint(
            document_id=71171,
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Mont Granier',
                    description='...',
                    summary='Le Mont [b]Granier[/b]'),
                WaypointLocale(
                    lang='en', title='Mont Granier',
                    description='...',
                    summary='The Mont Granier')
            ])
        self.waypoint2 = Waypoint(
            document_id=71172,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.route1 = Route(
            document_id=71173,
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            locales=[
                RouteLocale(
                    lang='en', title='Face N',
                    description='...', gear='paraglider',
                    title_prefix='Mont Blanc'
                )
            ]
        )
        self.waypoint3 = Waypoint(
            document_id=71174,
            redirects_to=71171,
            waypoint_type='summit', elevation=4985,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe')
            ])
        self.session.add_all([
            self.waypoint1, self.waypoint2, self.waypoint3, self.route1])
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.waypoint1, user_id)
        DocumentRest.create_new_version(self.waypoint2, user_id)
        DocumentRest.create_new_version(self.waypoint3, user_id)
        DocumentRest.create_new_version(self.route1, user_id)
