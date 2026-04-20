from datetime import date, timedelta
from unittest.mock import patch

import pytest

from c2corg_api.models import es_sync
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.es_sync import ESDeletedLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.sync import (
    create_search_documents,
    get_changed_documents,
    get_changed_documents_for_associations,
    get_changed_users,
    get_deleted_locale_documents,
    get_documents_per_type,
    sync_deleted_documents,
    sync_documents,
)
from c2corg_api.tests import BaseTestCase, global_userids
from c2corg_api.views.document import DocumentRest


class SyncTest(BaseTestCase):
    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_get_changed_documents(self):
        last_update, _ = es_sync.get_status(self.session)

        changed_documents = get_changed_documents(self.session, last_update)
        assert len(changed_documents) == 5
        assert 'o' == changed_documents[0][1]
        assert 'r' == changed_documents[1][1]
        assert 'w' == changed_documents[2][1]

        assert (
            len(get_changed_documents(self.session, last_update + timedelta(0, 1))) == 0
        )

    def test_get_changed_documents_for_associations(self):
        last_update, _ = es_sync.get_status(self.session)

        changed_documents = get_changed_documents_for_associations(
            self.session, last_update
        )
        assert len(changed_documents) == 4
        assert changed_documents[0][0] == self.route1.document_id
        assert changed_documents[1][0] == self.outing1.document_id
        assert changed_documents[2][0] == self.route1.document_id
        assert changed_documents[3][0] == self.outing1.document_id

        assert (
            len(
                get_changed_documents_for_associations(
                    self.session, last_update + timedelta(0, 1)
                )
            )
            == 0
        )

    def test_get_changed_users(self):
        user_id = global_userids['contributor']
        user = self.session.get(User, user_id)
        user.name = 'changed'
        self.session.flush()

        last_update, _ = es_sync.get_status(self.session)

        changed_users = get_changed_users(self.session, last_update)
        assert len(changed_users) == 1
        assert user_id == changed_users[0][0]
        assert 'u' == changed_users[0][1]

        assert (
            len(get_changed_documents(self.session, last_update + timedelta(0, 1))) == 0
        )

    def test_get_deleted_locale_documents(self):
        # simulate removing a locale
        self.session.add(
            ESDeletedLocale(document_id=self.waypoint1.document_id, type='w', lang='fr')
        )
        self.session.flush()

        last_update, _ = es_sync.get_status(self.session)

        changed_documents = get_deleted_locale_documents(self.session, last_update)

        assert len(changed_documents) == 1
        assert 'w' == changed_documents[0][1]

    def test_get_documents_per_type(self):
        changed_documents = [(1, 'r'), (2, 'w'), (3, 'r'), (4, 'r'), (4, 'r')]
        docs_per_type = get_documents_per_type(changed_documents)
        assert docs_per_type == {'r': {1, 3, 4}, 'w': {2}}

    def test_create_search_documents(self):
        search_documents = []
        batch_mock = self._create_mock_match(search_documents)(None, 1000)

        self.route1.geometry = DocumentGeometry()
        self.route1.geometry.lon_lat = '{"type": "Point", "coordinates": [6, 46]}'
        create_search_documents('r', [self.route1], batch_mock)
        doc = search_documents[0]

        assert doc['_op_type'] == 'index'
        assert doc['_id'] == self.route1.document_id
        assert doc['title_en'] == 'Mont Blanc : Face N'
        assert doc['geom'] == [6, 46]

    def test_create_search_documents_user_profile(self):
        search_documents = []
        batch_mock = self._create_mock_match(search_documents)(None, 1000)

        document_id = global_userids['contributor']
        user_profile = self.session.get(UserProfile, document_id)

        create_search_documents('u', [user_profile], batch_mock)
        doc = search_documents[0]

        assert doc['_op_type'] == 'index'
        assert doc['_id'] == document_id
        assert doc['title_en'] == 'Contributor contributor'
        assert doc['title_fr'] == 'Contributor contributor'

    @patch('c2corg_api.scripts.es.sync.ElasticBatch')
    def test_sync_documents(self, mock):
        search_documents = []
        mock.side_effect = self._create_mock_match(search_documents)

        # test that unconfirmed users are ignored
        user_id = global_userids['contributor2']
        user = self.session.get(User, user_id)
        user.email_validated = False
        self.session.flush()

        changed_documents = [
            (self.waypoint1.document_id, 'w'),
            (self.waypoint2.document_id, 'w'),
            (self.waypoint3.document_id, 'w'),
            (self.route1.document_id, 'r'),
            (self.outing1.document_id, 'o'),
            (user_id, 'u'),
        ]
        sync_documents(self.session, changed_documents, 1000)
        assert len(search_documents) == 5

        redirected_doc = self._get_by_id(search_documents, self.waypoint3.document_id)
        assert redirected_doc['_op_type'] == 'delete'

        waypoint1_doc = self._get_by_id(search_documents, self.waypoint1.document_id)
        assert waypoint1_doc['geom'][0] == pytest.approx(5.71288995)
        assert waypoint1_doc['geom'][1] == pytest.approx(45.64476395)

        route_doc = self._get_by_id(search_documents, self.route1.document_id)
        assert route_doc['title_en'] == 'Mont Blanc : Face N'
        assert set(route_doc['waypoints']) == {
            self.waypoint1.document_id,
            self.waypoint2.document_id,
        }

        outing_doc = self._get_by_id(search_documents, self.outing1.document_id)
        assert outing_doc['title_en'] == '...'
        assert set(outing_doc['waypoints']) == {
            self.waypoint1.document_id,
            self.waypoint2.document_id,
        }

    @patch('c2corg_api.scripts.es.sync.ElasticBatch')
    def test_sync_deleted_documents(self, mock):
        search_documents = []
        mock.side_effect = self._create_mock_match(search_documents)

        deleted_documents = [
            (self.waypoint1.document_id, 'w'),
            (self.route1.document_id, 'r'),
            (self.outing1.document_id, 'o'),
        ]
        sync_deleted_documents(self.session, deleted_documents, 1000)
        assert len(search_documents) == 3

        waypoint1_doc = self._get_by_id(search_documents, self.waypoint1.document_id)
        assert waypoint1_doc['_op_type'] == 'delete'

        route_doc = self._get_by_id(search_documents, self.route1.document_id)
        assert route_doc['_op_type'] == 'delete'

        outing_doc = self._get_by_id(search_documents, self.outing1.document_id)
        assert outing_doc['_op_type'] == 'delete'

    def _get_by_id(self, search_documents, document_id):
        return next(
            filter(lambda doc: doc['_id'] == document_id, search_documents), None
        )

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
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr',
                    title='Mont Granier',
                    description='...',
                    summary='Le Mont [b]Granier[/b]',
                ),
                WaypointLocale(
                    lang='en',
                    title='Mont Granier',
                    description='...',
                    summary='The Mont Granier',
                ),
            ],
        )
        self.waypoint2 = Waypoint(
            document_id=71172,
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
        self.route1 = Route(
            document_id=71173,
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=800,
            height_diff_down=800,
            durations=['1'],
            locales=[
                RouteLocale(
                    lang='en',
                    title='Face N',
                    description='...',
                    gear='paraglider',
                    title_prefix='Mont Blanc',
                )
            ],
        )
        self.waypoint3 = Waypoint(
            document_id=71174,
            redirects_to=71171,
            waypoint_type='summit',
            elevation=4985,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='en',
                    title='Mont Blanc',
                    description='...',
                    summary='The heighest point in Europe',
                )
            ],
        )
        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            locales=[
                OutingLocale(lang='en', title='...', description='...', weather='sunny')
            ],
        )
        self.session.add_all(
            [self.waypoint1, self.waypoint2, self.waypoint3, self.route1, self.outing1]
        )
        self.session.flush()

        user_id = global_userids['contributor']
        DocumentRest.create_new_version(self.waypoint1, user_id)
        DocumentRest.create_new_version(self.waypoint2, user_id)
        DocumentRest.create_new_version(self.waypoint3, user_id)
        DocumentRest.create_new_version(self.route1, user_id)
        DocumentRest.create_new_version(self.outing1, user_id)

        association_wr = Association.create(self.waypoint1, self.route1)
        association_ww = Association.create(self.waypoint2, self.waypoint1)
        association_ro = Association.create(self.route1, self.outing1)
        user = self.session.get(UserProfile, global_userids['contributor'])
        association_uo = Association.create(user, self.outing1)
        self.session.add_all(
            [
                association_wr,
                association_ww,
                association_ro,
                association_uo,
                association_wr.get_log(user_id),
                association_ww.get_log(user_id),
                association_ro.get_log(user_id),
                association_uo.get_log(user_id),
            ]
        )
        self.session.flush()
