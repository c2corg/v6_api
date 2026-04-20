"""
Tests for the FastAPI validation helpers in
``c2corg_api.routers.helpers.validation``.

Mirrors ``c2corg_api/tests/views/test_validation.py``.
The router layer wraps the same ``validate_associations_in`` logic
and exposes ``validate_associations(…, db=session)`` — these tests
exercise that wrapper to ensure the FastAPI code path behaves
identically.

Also tests ``parse_datetime`` which is still imported from
``c2corg_api.views.validation``.
"""

from dateutil import parser as datetime_parser

from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE, Route
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.routers.helpers.validation import parse_datetime, validate_associations
from c2corg_api.tests import BaseTestCase


class TestValidationRouter(BaseTestCase):
    """Unit tests for the router-layer validation helpers."""

    def setUp(self):
        super().setUp()

        self.waypoint1 = Waypoint(waypoint_type='summit')
        self.waypoint2 = Waypoint(waypoint_type='summit')
        self.route1 = Route(activities=['hiking'])
        self.route2 = Route(activities=['hiking'])
        self.user_profile1 = UserProfile()
        self.user_profile2 = UserProfile()
        self.session.add_all(
            [
                self.waypoint1,
                self.waypoint2,
                self.route1,
                self.route2,
                self.user_profile1,
                self.user_profile2,
            ]
        )
        self.session.flush()

    # ── Association validation ────────────────────────────────────

    def test_validate_associations_outing(self):
        associations_in = {
            'routes': [
                {'document_id': self.route1.document_id},
                {'document_id': self.route2.document_id},
            ],
            'users': [{'document_id': self.user_profile1.document_id}],
            'waypoints': [{'document_id': 'waypoints are ignored'}],
        }

        associations, errors = validate_associations(
            associations_in, OUTING_TYPE, db=self.session
        )

        assert len(errors) == 0

        expected = {
            'users': [
                {'document_id': self.user_profile1.document_id, 'is_parent': True}
            ],
            'routes': [
                {'document_id': self.route1.document_id, 'is_parent': True},
                {'document_id': self.route2.document_id, 'is_parent': True},
            ],
        }
        assert associations == expected

    def test_validate_associations_waypoint(self):
        associations_in = {
            'routes': [{'document_id': self.route1.document_id}],
            'waypoints': [{'document_id': self.waypoint1.document_id}],
            'waypoint_children': [{'document_id': self.waypoint2.document_id}],
            'outings': [{'document_id': 'outings are ignored'}],
        }

        associations, errors = validate_associations(
            associations_in, WAYPOINT_TYPE, db=self.session
        )

        assert len(errors) == 0

        expected = {
            'waypoints': [
                {'document_id': self.waypoint1.document_id, 'is_parent': True}
            ],
            'waypoint_children': [
                {'document_id': self.waypoint2.document_id, 'is_parent': False}
            ],
        }
        assert associations == expected

    def test_validate_associations_route(self):
        associations_in = {
            'routes': [
                {'document_id': self.route1.document_id},
                {'document_id': self.route2.document_id},
            ],
            'waypoints': [{'document_id': self.waypoint1.document_id}],
        }

        associations, errors = validate_associations(
            associations_in, ROUTE_TYPE, db=self.session
        )

        assert len(errors) == 0

        expected = {
            'routes': [
                {'document_id': self.route1.document_id, 'is_parent': False},
                {'document_id': self.route2.document_id, 'is_parent': False},
            ],
            'waypoints': [
                {'document_id': self.waypoint1.document_id, 'is_parent': True}
            ],
        }
        assert associations == expected

    def test_validate_associations_invalid_type(self):
        associations_in = {
            'users': [
                {'document_id': self.user_profile1.document_id, 'is_parent': True}
            ]
        }

        associations, errors = validate_associations(
            associations_in, WAYPOINT_TYPE, db=self.session
        )

        # users are ignored for waypoints
        assert associations == {}

    def test_validate_associations_invalid_document_id(self):
        associations_in = {'waypoints': [{'document_id': -99999}]}

        associations, errors = validate_associations(
            associations_in, WAYPOINT_TYPE, db=self.session
        )

        assert associations is None
        assert len(errors) == 1
        error = errors[0]
        assert error['name'] == 'associations.waypoints'
        assert (
            error['description'] == 'document "-99999" does not exist or is redirected'
        )

    def test_validate_associations_invalid_document_type(self):
        associations_in = {'routes': [{'document_id': self.waypoint1.document_id}]}

        associations, errors = validate_associations(
            associations_in, ROUTE_TYPE, db=self.session
        )

        assert associations is None
        assert len(errors) == 1
        error = errors[0]
        assert error['name'] == 'associations.routes'
        assert (
            error['description']
            == f'document "{self.waypoint1.document_id}" is not of type "r"'
        )

    # ── parse_datetime ────────────────────────────────────────────

    def test_parse_datetime(self):
        assert parse_datetime(None) is None
        assert parse_datetime('2016-11-28T23:57:30.090459+01:00') == (
            datetime_parser.parse('2016-11-28T23:57:30.090459+01:00')
        )
        assert parse_datetime('2016-11-28T23%3A57%3A30.090459%2B01%3A00') == (
            datetime_parser.parse('2016-11-28T23:57:30.090459+01:00')
        )
