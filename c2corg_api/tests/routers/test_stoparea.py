"""
Tests for the FastAPI Stoparea router (``/v2/stopareas``).

There are no Pyramid view tests to mirror, so these are new tests
covering the most important endpoints.

Note: The DB column (migration ``bb61456d557f``) uses ``srid=3857``.
Production inserts are done via raw SQL (the Navitia job in ``__init__.py``
and shell scripts) which do ``ST_Transform(..., 3857)``.  We use raw SQL
here too to match the production insertion pattern.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from c2corg_api.database import get_db
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.tests import BaseTestCase
from c2corg_api.tests.routers import get_real_app


class TestStopareaRouter(BaseTestCase):
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
        # Raw SQL because model declares srid=4326 but DB column is 3857.
        # See module docstring.
        self.session.execute(
            text("""
            INSERT INTO guidebook.stopareas
                (navitia_id, stoparea_name, line, operator, geom)
            VALUES
                ('stop_area:OIF:SA:8738400', 'Chamonix Mont-Blanc',
                 'line_A', 'SNCF',
                 ST_GeomFromText('POINT(764952 5765204)', 3857)),
                ('stop_area:OIF:SA:8700001', 'Grenoble Gare',
                 'line_B', 'RATP',
                 ST_GeomFromText('POINT(636098 5658953)', 3857)),
                ('stop_area:OIF:SA:0000000', 'No Geom Stop',
                 'line_C', 'Other', NULL)
        """)
        )
        self.session.flush()

        # Fetch them back as ORM objects for use in assertions.
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
        self.stoparea_no_geom = (
            self.session.query(Stoparea)
            .filter(Stoparea.navitia_id == 'stop_area:OIF:SA:0000000')
            .one()
        )

    # ── GET /v2/stopareas ────────────────────────────────────

    def test_collection_get(self):
        r = self.client.get('/v2/stopareas')
        assert r.status_code == 200
        body = r.json()
        assert 'documents' in body
        assert 'total_results' in body
        assert body['total_results'] == 3
        assert len(body['documents']) == 3

    def test_collection_get_pagination(self):
        r = self.client.get('/v2/stopareas?page_id=1&nb_items=2')
        assert r.status_code == 200
        body = r.json()
        assert body['total_results'] == 3
        assert len(body['documents']) == 2

    def test_collection_get_page2(self):
        r = self.client.get('/v2/stopareas?page_id=2&nb_items=2')
        assert r.status_code == 200
        body = r.json()
        assert body['total_results'] == 3
        assert len(body['documents']) == 1

    # ── GET /v2/stopareas/{id} ───────────────────────────────

    def test_get_stoparea(self):
        r = self.client.get('/v2/stopareas/{}'.format(self.stoparea1.stoparea_id))
        assert r.status_code == 200
        body = r.json()
        assert body['navitia_id'] == 'stop_area:OIF:SA:8738400'
        assert body['stoparea_name'] == 'Chamonix Mont-Blanc'
        assert body['line'] == 'line_A'
        assert body['operator'] == 'SNCF'
        assert body['coordinates'] is not None
        assert body['coordinates']['x'] == pytest.approx(764952, abs=0.5)
        assert body['coordinates']['y'] == pytest.approx(5765204, abs=0.5)

    def test_get_stoparea_no_geom(self):
        r = self.client.get(
            '/v2/stopareas/{}'.format(self.stoparea_no_geom.stoparea_id)
        )
        assert r.status_code == 200
        body = r.json()
        assert body['stoparea_name'] == 'No Geom Stop'
        assert body['coordinates'] is None

    def test_get_stoparea_not_found(self):
        r = self.client.get('/v2/stopareas/999999')
        assert r.status_code == 404

    # ── GET /v2/stopareas/{id}/{lang}/info ───────────────────

    def test_get_stoparea_info(self):
        r = self.client.get(
            '/v2/stopareas/{}/fr/info'.format(self.stoparea1.stoparea_id)
        )
        assert r.status_code == 200
        body = r.json()
        assert body['stoparea_id'] == self.stoparea1.stoparea_id
        assert 'attributes' in body
        attrs = body['attributes']
        assert attrs['navitia_id'] == 'stop_area:OIF:SA:8738400'
        assert attrs['stoparea_name'] == 'Chamonix Mont-Blanc'

    def test_get_stoparea_info_not_found(self):
        r = self.client.get('/v2/stopareas/999999/fr/info')
        assert r.status_code == 404
