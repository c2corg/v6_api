from dataclasses import dataclass

import pytest

from c2corg_api.models.association import (
    Association,
    _diff_associations,
    _get_current_associations,
    synchronize_associations,
)
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    route1: Route
    route2: Route
    user_profile1: UserProfile
    user_profile2: UserProfile


@pytest.fixture
def docs(session) -> Docs:
    waypoint1 = Waypoint(waypoint_type='summit')
    waypoint2 = Waypoint(waypoint_type='summit')
    route1 = Route(activities=['hiking'])
    route2 = Route(activities=['hiking'])
    user_profile1 = UserProfile()
    user_profile2 = UserProfile()
    session.add_all(
        [
            waypoint1,
            waypoint2,
            route1,
            route2,
            user_profile1,
            user_profile2,
        ]
    )
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        route1=route1,
        route2=route2,
        user_profile1=user_profile1,
        user_profile2=user_profile2,
    )


def _add_test_data_routes(docs, session):
    session.add_all(
        [
            Association.create(parent_document=docs.route1, child_document=docs.route2),
            Association.create(
                parent_document=docs.waypoint1, child_document=docs.route1
            ),
            Association.create(
                parent_document=docs.waypoint2, child_document=docs.route1
            ),
        ]
    )
    session.flush()


def test_get_current_associations_routes(session, docs):
    _add_test_data_routes(docs, session)

    new_associations = {
        'routes': [{'document_id': 1, 'is_parent': True}],
        'waypoints': [{'document_id': 2, 'is_parent': True}],
    }

    current_associations = _get_current_associations(docs.route1, new_associations)

    expected_current_associations = {
        'routes': [{'document_id': docs.route2.document_id, 'is_parent': False}],
        'waypoints': [
            {'document_id': docs.waypoint1.document_id, 'is_parent': True},
            {'document_id': docs.waypoint2.document_id, 'is_parent': True},
        ],
    }
    assert current_associations == expected_current_associations


def test_get_current_associations_routes_partial(session, docs):
    """Check that only those types are loaded that are also given in the
    new associations (e.g. waypoints are not loaded in this case because
    the type is not given as input).
    """
    _add_test_data_routes(docs, session)

    new_associations = {'routes': [{'document_id': 1, 'is_parent': True}]}

    current_associations = _get_current_associations(docs.route1, new_associations)

    expected_current_associations = {
        'routes': [{'document_id': docs.route2.document_id, 'is_parent': False}]
    }
    assert current_associations == expected_current_associations


def test_get_current_associations_waypoints(session, docs):
    waypoint3 = Waypoint(waypoint_type='summit')
    session.add(waypoint3)
    session.flush()
    session.add_all(
        [
            Association.create(
                parent_document=docs.waypoint1, child_document=docs.waypoint2
            ),
            Association.create(
                parent_document=waypoint3, child_document=docs.waypoint1
            ),
            Association.create(
                parent_document=docs.waypoint1, child_document=docs.route1
            ),
            Association.create(
                parent_document=docs.waypoint1, child_document=docs.route2
            ),
        ]
    )
    session.flush()

    new_associations = {
        # routes are ignored
        'routes': [
            {'document_id': 1, 'is_parent': True},
            {'document_id': 2, 'is_parent': True},
        ],
        'waypoints': [{'document_id': 3, 'is_parent': True}],
        'waypoint_children': [{'document_id': 4, 'is_parent': False}],
    }

    current_associations = _get_current_associations(docs.waypoint1, new_associations)

    expected_current_associations = {
        'waypoints': [{'document_id': waypoint3.document_id, 'is_parent': True}],
        'waypoint_children': [
            {'document_id': docs.waypoint2.document_id, 'is_parent': False}
        ],
    }
    assert current_associations == expected_current_associations


def test_get_current_associations_waypoints_partial(session, docs):
    session.add(
        Association.create(
            parent_document=docs.waypoint1, child_document=docs.waypoint2
        )
    )
    session.flush()

    new_associations = {}
    current_associations = _get_current_associations(docs.waypoint1, new_associations)

    expected_current_associations = {}
    assert current_associations == expected_current_associations


def test_diff_associations(docs):
    new_associations = {
        'routes': [
            {'document_id': 1, 'is_parent': True},
            {'document_id': 2, 'is_parent': True},
        ],
        'waypoints': [{'document_id': 3, 'is_parent': False}],
    }
    current_associations = {
        'routes': [
            {'document_id': 1, 'is_parent': True},
            {'document_id': 4, 'is_parent': True},
        ],
        'waypoints': [],
    }

    to_add, to_remove = _diff_associations(new_associations, current_associations)

    expected_to_add = [
        {'document_id': 2, 'is_parent': True, 'doc_type': ROUTE_TYPE},
        {'document_id': 3, 'is_parent': False, 'doc_type': WAYPOINT_TYPE},
    ]

    expected_to_remove = [{'document_id': 4, 'is_parent': True, 'doc_type': ROUTE_TYPE}]

    assert _get_document_ids(to_add) == _get_document_ids(expected_to_add)
    assert _get_document_ids(to_remove) == _get_document_ids(expected_to_remove)


def test_synchronize_associations(session, user_ids, docs):
    route3 = Route(activities=['hiking'])
    route4 = Route(activities=['hiking'])
    session.add_all([route3, route4])
    session.flush()
    session.add_all(
        [
            Association.create(parent_document=docs.route1, child_document=docs.route2),
            Association.create(parent_document=docs.route1, child_document=route3),
        ]
    )
    session.flush()

    new_associations = {
        'routes': [
            {'document_id': docs.route2.document_id, 'is_parent': True},
            {'document_id': route4.document_id, 'is_parent': True},
        ],
        'waypoints': [{'document_id': docs.waypoint1.document_id, 'is_parent': True}],
    }
    synchronize_associations(docs.route1, new_associations, user_ids['contributor'])

    assert _get_association(session, docs.route1, docs.route2) is not None
    assert _get_association(session, route4, docs.route1) is not None
    assert _get_association(session, docs.route2, docs.route1) is None
    assert _get_association(session, docs.route1, route3) is None
    assert _get_association(session, docs.waypoint1, docs.route1) is not None


def _get_association(session, main_doc, child_doc):
    return session.get(Association, (main_doc.document_id, child_doc.document_id))


def _get_document_ids(docs):
    return {d['document_id'] for d in docs}
