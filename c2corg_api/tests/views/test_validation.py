from dataclasses import dataclass

import pytest
from dateutil import parser as datetime_parser

from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.views.resource import Errors
from c2corg_api.views.validation import parse_datetime, validate_associations_in


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    route1: Route
    route2: Route
    user_profile1: UserProfile
    user_profile2: UserProfile


@pytest.fixture(autouse=True)
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


def test_validate_associations_outing(docs):
    associations_in = {
        'routes': [
            {'document_id': docs.route1.document_id},
            {'document_id': docs.route2.document_id},
        ],
        'users': [{'document_id': docs.user_profile1.document_id}],
        'waypoints': [{'document_id': 'waypoints are ignored'}],
    }

    errors = Errors()
    associations = validate_associations_in(associations_in, OUTING_TYPE, errors)

    assert len(errors) == 0

    expected_associations = {
        'users': [{'document_id': docs.user_profile1.document_id, 'is_parent': True}],
        'routes': [
            {'document_id': docs.route1.document_id, 'is_parent': True},
            {'document_id': docs.route2.document_id, 'is_parent': True},
        ],
    }
    assert associations == expected_associations


def test_validate_associations_waypoint(docs):
    associations_in = {
        # routes are ignored
        'routes': [{'document_id': docs.route1.document_id}],
        'waypoints': [{'document_id': docs.waypoint1.document_id}],
        'waypoint_children': [{'document_id': docs.waypoint2.document_id}],
        'outings': [{'document_id': 'outings are ignored'}],
    }

    errors = Errors()
    associations = validate_associations_in(associations_in, WAYPOINT_TYPE, errors)

    assert len(errors) == 0

    expected_associations = {
        'waypoints': [{'document_id': docs.waypoint1.document_id, 'is_parent': True}],
        'waypoint_children': [
            {'document_id': docs.waypoint2.document_id, 'is_parent': False}
        ],
    }
    assert associations == expected_associations


def test_validate_associations_route(docs):
    associations_in = {
        'routes': [
            {'document_id': docs.route1.document_id},
            {'document_id': docs.route2.document_id},
        ],
        'waypoints': [{'document_id': docs.waypoint1.document_id}],
    }

    errors = Errors()
    associations = validate_associations_in(associations_in, ROUTE_TYPE, errors)

    assert len(errors) == 0

    expected_associations = {
        'routes': [
            {'document_id': docs.route1.document_id, 'is_parent': False},
            {'document_id': docs.route2.document_id, 'is_parent': False},
        ],
        'waypoints': [{'document_id': docs.waypoint1.document_id, 'is_parent': True}],
    }
    assert associations == expected_associations


def test_validate_associations_invalid_type(docs):
    associations_in = {
        'users': [{'document_id': docs.user_profile1.document_id, 'is_parent': True}]
    }

    errors = Errors()
    associations = validate_associations_in(associations_in, WAYPOINT_TYPE, errors)

    # users are ignored for waypoints
    assert associations == {}


def test_validate_associations_invalid_document_id():
    associations_in = {'waypoints': [{'document_id': -99999}]}

    errors = Errors()
    associations = validate_associations_in(associations_in, WAYPOINT_TYPE, errors)

    assert associations is None
    assert len(errors) == 1
    error = errors[0]
    assert error['name'] == 'associations.waypoints'
    assert error['description'] == 'document "-99999" does not exist or is redirected'


def test_validate_associations_invalid_document_type(docs):
    associations_in = {'routes': [{'document_id': docs.waypoint1.document_id}]}

    errors = Errors()
    associations = validate_associations_in(associations_in, ROUTE_TYPE, errors)

    assert associations is None
    assert len(errors) == 1
    error = errors[0]
    assert error['name'] == 'associations.routes'
    assert (
        error['description']
        == 'document "' + str(docs.waypoint1.document_id) + '" is not of type "r"'
    )


def test_parse_datetime():
    assert parse_datetime(None) is None
    assert parse_datetime('2016-11-28T23:57:30.090459+01:00') == datetime_parser.parse(
        '2016-11-28T23:57:30.090459+01:00'
    )

    assert parse_datetime(
        '2016-11-28T23%3A57%3A30.090459%2B01%3A00'
    ) == datetime_parser.parse('2016-11-28T23:57:30.090459+01:00')
