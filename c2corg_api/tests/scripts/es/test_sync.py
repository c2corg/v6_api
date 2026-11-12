import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from sqlalchemy import event

from c2corg_api.models import es_sync
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.es.sync import (
    SYNC_OVERLAP,
    create_search_documents,
    get_changed_documents,
    get_changed_documents_for_associations,
    get_changed_routes_and_outings_wr,
    get_changed_users,
    get_deleted_locale_documents,
    get_documents,
    get_documents_per_type,
    sync_deleted_documents,
    sync_documents,
    sync_es,
)
from c2corg_api.tests import global_userids
from c2corg_api.views.document import create_new_version


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    route1: Route
    waypoint3: Waypoint
    outing1: Outing


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    _, date_now = es_sync.get_status(session)
    es_sync.mark_as_updated(session, date_now)

    waypoint1 = Waypoint(
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
    waypoint2 = Waypoint(
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
    route1 = Route(
        document_id=71173,
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
        durations='1',
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
    waypoint3 = Waypoint(
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
    outing1 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        locales=[
            OutingLocale(lang='en', title='...', description='...', weather='sunny')
        ],
    )
    session.add_all([waypoint1, waypoint2, waypoint3, route1, outing1])
    session.flush()

    user_id = user_ids['contributor']
    create_new_version(waypoint1, user_id)
    create_new_version(waypoint2, user_id)
    create_new_version(waypoint3, user_id)
    create_new_version(route1, user_id)
    create_new_version(outing1, user_id)

    association_wr = Association.create(waypoint1, route1)
    association_ww = Association.create(waypoint2, waypoint1)
    association_ro = Association.create(route1, outing1)
    user = session.get(UserProfile, user_ids['contributor'])
    association_uo = Association.create(user, outing1)
    session.add_all(
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
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        route1=route1,
        waypoint3=waypoint3,
        outing1=outing1,
    )


def test_get_changed_documents(session):
    last_update, _ = es_sync.get_status(session)

    changed_documents = get_changed_documents(session, last_update)
    assert len(changed_documents) == 5
    assert 'o' == changed_documents[0][1]
    assert 'r' == changed_documents[1][1]
    assert 'w' == changed_documents[2][1]

    assert (
        len(get_changed_documents(session, last_update + datetime.timedelta(0, 1))) == 0
    )


def test_get_changed_documents_for_associations(session, docs):
    last_update, _ = es_sync.get_status(session)

    changed_documents = get_changed_documents_for_associations(session, last_update)
    # W1 -> R1 and W2 -> W1 give R1 and O1 each, R1 -> O1 and U -> O1 give O1
    assert sorted(changed_documents) == sorted(
        [
            (docs.route1.document_id, 'r'),
            (docs.outing1.document_id, 'o'),
            (docs.route1.document_id, 'r'),
            (docs.outing1.document_id, 'o'),
            (docs.outing1.document_id, 'o'),
        ]
    )

    assert (
        len(
            get_changed_documents_for_associations(
                session, last_update + datetime.timedelta(0, 1)
            )
        )
        == 0
    )


def test_get_changed_routes_and_outings_wr(session, docs):
    last_update, _ = es_sync.get_status(session)

    # the outings of R1 list the waypoints of R1, so they have to be
    # updated too when W1 -> R1 changes
    changed_documents = get_changed_routes_and_outings_wr(session, last_update)
    assert sorted(changed_documents) == sorted(
        [
            (docs.route1.document_id, 'r'),
            (docs.outing1.document_id, 'o'),
        ]
    )

    assert (
        get_changed_routes_and_outings_wr(
            session, last_update + datetime.timedelta(0, 1)
        )
        == []
    )


def test_get_changed_users(session, user_ids):
    user_id = user_ids['contributor']
    user = session.get(User, user_id)
    user.name = 'changed'
    session.flush()

    last_update, _ = es_sync.get_status(session)

    changed_users = get_changed_users(session, last_update)
    assert len(changed_users) == 1
    assert user_id == changed_users[0][0]
    assert 'u' == changed_users[0][1]

    assert (
        len(get_changed_documents(session, last_update + datetime.timedelta(0, 1))) == 0
    )


def test_get_deleted_locale_documents(session, docs):
    # simulate removing a locale
    session.add(
        ESDeletedLocale(document_id=docs.waypoint1.document_id, type='w', lang='fr')
    )
    session.flush()

    last_update, _ = es_sync.get_status(session)

    changed_documents = get_deleted_locale_documents(session, last_update)

    assert len(changed_documents) == 1
    assert 'w' == changed_documents[0][1]


def test_get_documents_reads_only_the_given_ids(db_connection, session, docs):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    # a chunk size of 1: one query per document
    ids = {docs.waypoint2.document_id, docs.waypoint1.document_id}
    event.listen(db_connection, 'before_cursor_execute', record)
    try:
        found = list(get_documents(session, 'w', 1, ids))
    finally:
        event.remove(db_connection, 'before_cursor_execute', record)

    # no window over the whole documents table, as for fill_index
    assert not [s for s in statements if 'row_number' in s]
    assert [doc.document_id for doc in found] == sorted(ids)


def test_get_documents_all(session, docs):
    found = list(get_documents(session, 'w', 1, ignore_redirects=True))

    found_ids = [doc.document_id for doc in found]
    assert docs.waypoint1.document_id in found_ids
    assert docs.waypoint2.document_id in found_ids
    assert docs.waypoint3.document_id not in found_ids


def test_get_documents_per_type():
    changed_documents = [(1, 'r'), (2, 'w'), (3, 'r'), (4, 'r'), (4, 'r')]
    docs_per_type = get_documents_per_type(changed_documents)
    assert docs_per_type == {'r': {1, 3, 4}, 'w': {2}}


def test_create_search_documents(docs):
    search_documents = []
    batch_mock = _create_mock_match(search_documents)(None, 1000)

    docs.route1.geometry = DocumentGeometry()
    docs.route1.geometry.lon_lat = '{"type": "Point", "coordinates": [6, 46]}'
    create_search_documents('r', [docs.route1], batch_mock)
    doc = search_documents[0]

    assert doc['_op_type'] == 'index'
    assert doc['_id'] == docs.route1.document_id
    assert doc['title_en'] == 'Mont Blanc : Face N'
    # self.assertEqual(doc['description_en'], '...')
    assert doc['geom'] == [6, 46]


def test_create_search_documents_user_profile(session):
    search_documents = []
    batch_mock = _create_mock_match(search_documents)(None, 1000)

    document_id = global_userids['contributor']
    user_profile = session.get(UserProfile, document_id)

    create_search_documents('u', [user_profile], batch_mock)
    doc = search_documents[0]

    assert doc['_op_type'] == 'index'
    assert doc['_id'] == document_id
    assert doc['title_en'] == 'Contributor contributor'
    # self.assertEqual(doc['description_en'], 'Me')
    assert doc['title_fr'] == 'Contributor contributor'
    # self.assertEqual(doc['description_fr'], 'Moi')


@patch('c2corg_api.scripts.es.sync.ElasticBatch')
def test_sync_documents(mock, session, user_ids, docs):
    search_documents = []
    mock.side_effect = _create_mock_match(search_documents)

    # test that unconfirmed users are ignored
    user_id = user_ids['contributor2']
    user = session.get(User, user_id)
    user.email_validated = False
    session.flush()

    changed_documents = [
        (docs.waypoint1.document_id, 'w'),
        (docs.waypoint2.document_id, 'w'),
        (docs.waypoint3.document_id, 'w'),
        (docs.route1.document_id, 'r'),
        (docs.outing1.document_id, 'o'),
        (user_id, 'u'),
    ]
    sync_documents(session, changed_documents, 1000)
    assert len(search_documents) == 5

    redirected_doc = _get_by_id(search_documents, docs.waypoint3.document_id)
    assert redirected_doc['_op_type'] == 'delete'

    waypoint1_doc = _get_by_id(search_documents, docs.waypoint1.document_id)
    assert waypoint1_doc['geom'][0] == pytest.approx(5.71288995, abs=5e-8)
    assert waypoint1_doc['geom'][1] == pytest.approx(45.64476395, abs=5e-8)

    route_doc = _get_by_id(search_documents, docs.route1.document_id)
    assert route_doc['title_en'] == 'Mont Blanc : Face N'
    assert set(route_doc['waypoints']) == {
        docs.waypoint1.document_id,
        docs.waypoint2.document_id,
    }

    outing_doc = _get_by_id(search_documents, docs.outing1.document_id)
    assert outing_doc['title_en'] == '...'
    assert set(outing_doc['waypoints']) == {
        docs.waypoint1.document_id,
        docs.waypoint2.document_id,
    }


@patch('c2corg_api.scripts.es.sync.ElasticBatch')
def test_sync_deleted_documents(mock, session, docs):
    search_documents = []
    mock.side_effect = _create_mock_match(search_documents)

    deleted_documents = [
        (docs.waypoint1.document_id, 'w'),
        (docs.route1.document_id, 'r'),
        (docs.outing1.document_id, 'o'),
    ]
    sync_deleted_documents(session, deleted_documents, 1000)
    assert len(search_documents) == 3

    waypoint1_doc = _get_by_id(search_documents, docs.waypoint1.document_id)
    assert waypoint1_doc['_op_type'] == 'delete'

    route_doc = _get_by_id(search_documents, docs.route1.document_id)
    assert route_doc['_op_type'] == 'delete'

    outing_doc = _get_by_id(search_documents, docs.outing1.document_id)
    assert outing_doc['_op_type'] == 'delete'


@pytest.mark.parametrize(
    ('age', 'synced'),
    [
        (datetime.timedelta(minutes=1), True),
        (SYNC_OVERLAP + datetime.timedelta(minutes=1), False),
    ],
)
@patch('c2corg_api.scripts.es.sync.ElasticBatch')
def test_sync_es_reads_late_commits(mock, session, docs, age, synced):
    """Sync a change committed after the last sync with an older timestamp."""
    # a deletion whose transaction started before the last sync and committed
    # after it: its `deleted_at` is older than `last_update`
    search_documents = []
    mock.side_effect = _create_mock_match(search_documents)
    last_update, _ = es_sync.get_status(session)
    session.add(
        ESDeletedDocument(document_id=987654, type='w', deleted_at=last_update - age)
    )
    session.flush()

    sync_es(session)

    deleted = _get_by_id(search_documents, 987654)
    assert (deleted is not None and deleted['_op_type'] == 'delete') is synced


def _get_by_id(search_documents, document_id):
    return next(filter(lambda doc: doc['_id'] == document_id, search_documents), None)


def _create_mock_match(actions):
    class MockBatch:
        def __init__(self, client, batch_size):
            pass

        def add(self, action):
            actions.append(action)

        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    return MockBatch
