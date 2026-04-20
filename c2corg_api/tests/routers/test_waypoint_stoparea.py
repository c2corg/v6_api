"""
Tests for the FastAPI Waypoint-Stoparea router.

Covers:
  - ``GET /v2/waypoints/{waypoint_id}/stopareas``
  - ``GET /v2/waypoints/{waypoint_id}/isReachable``

There are no Pyramid view tests to mirror, so these are new tests
covering the most important endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from c2corg_api.database import get_db
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.routers import get_real_app


class TestWaypointStopareaRouter(BaseTestCase):
    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
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

    def _add_test_data(self):
        # Create a waypoint
        self.waypoint = Waypoint(
            waypoint_type='access',
            locales=[DocumentLocale(lang='fr', title='Gare de Chamonix')],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(764952 5765204)'),
        )
        self.session.add(self.waypoint)
        self.session.flush()

        # A waypoint with no stopareas
        self.waypoint_empty = Waypoint(
            waypoint_type='access',
            locales=[DocumentLocale(lang='fr', title='Waypoint isolé')],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(700000 5700000)'),
        )
        self.session.add(self.waypoint_empty)
        self.session.flush()

        # Create stopareas — use raw SQL to match production insertion pattern
        # (Navitia job does ST_Transform(ST_SetSRID(ST_MakePoint(...), 4326), 3857))
        self.session.execute(
            text("""
            INSERT INTO guidebook.stopareas
                (navitia_id, stoparea_name, line, operator, geom)
            VALUES
                ('stop_area:OIF:SA:8738400', 'Chamonix Mont-Blanc',
                 'line_A', 'SNCF',
                 ST_GeomFromText('POINT(764952 5765204)', 3857)),
                ('stop_area:OIF:SA:8700001', 'Les Praz de Chamonix',
                 'line_B', 'SNCF',
                 ST_GeomFromText('POINT(766800 5766500)', 3857))
        """)
        )
        self.session.flush()

        self.stoparea1 = (
            self.session.query(Stoparea)
            .filter(Stoparea.navitia_id == 'stop_area:OIF:SA:8738400')
            .one()
        )
        self.stoparea2 = (
            self.session.query(Stoparea)
            .filter(Stoparea.navitia_id == 'stop_area:OIF:SA:8700001')
            .one()
        )

        # Link stopareas to the waypoint
        self.ws1 = WaypointStoparea(
            waypoint_id=self.waypoint.document_id,
            stoparea_id=self.stoparea1.stoparea_id,
            distance=120.5,
        )
        self.ws2 = WaypointStoparea(
            waypoint_id=self.waypoint.document_id,
            stoparea_id=self.stoparea2.stoparea_id,
            distance=850.0,
        )
        self.session.add_all([self.ws1, self.ws2])
        self.session.flush()

    # ── GET /v2/waypoints/{id}/stopareas ─────────────────────

    def test_get_stopareas_for_waypoint(self):
        r = self.client.get(
            '/v2/waypoints/{}/stopareas'.format(self.waypoint.document_id)
        )
        assert r.status_code == 200
        body = r.json()
        assert body['waypoint_id'] == self.waypoint.document_id
        assert len(body['stopareas']) == 2

        names = {s['stoparea_name'] for s in body['stopareas']}
        assert 'Chamonix Mont-Blanc' in names
        assert 'Les Praz de Chamonix' in names

        for s in body['stopareas']:
            assert 'distance' in s
            assert 'coordinates' in s

    def test_get_stopareas_distances(self):
        r = self.client.get(
            '/v2/waypoints/{}/stopareas'.format(self.waypoint.document_id)
        )
        body = r.json()
        distances = {s['stoparea_name']: s['distance'] for s in body['stopareas']}
        assert distances['Chamonix Mont-Blanc'] == pytest.approx(120.5)
        assert distances['Les Praz de Chamonix'] == pytest.approx(850.0)

    def test_get_stopareas_empty(self):
        r = self.client.get(
            '/v2/waypoints/{}/stopareas'.format(self.waypoint_empty.document_id)
        )
        assert r.status_code == 200
        body = r.json()
        assert body['stopareas'] == []

    def test_get_stopareas_nonexistent_waypoint(self):
        r = self.client.get('/v2/waypoints/999999/stopareas')
        assert r.status_code == 200
        body = r.json()
        assert body['stopareas'] == []

    # ── GET /v2/waypoints/{id}/isReachable ───────────────────

    def test_is_reachable_true(self):
        r = self.client.get(
            '/v2/waypoints/{}/isReachable'.format(self.waypoint.document_id)
        )
        assert r.status_code == 200
        assert r.json()

    def test_is_reachable_false(self):
        r = self.client.get(
            '/v2/waypoints/{}/isReachable'.format(self.waypoint_empty.document_id)
        )
        assert r.status_code == 200
        assert not r.json()

    def test_is_reachable_nonexistent_waypoint(self):
        r = self.client.get('/v2/waypoints/999999/isReachable')
        assert r.status_code == 200
        assert not r.json()
