"""
Tests for the FastAPI navitia router (``/v2/navitia/...``).

Mirrors the navitia-related tests from the Pyramid views.
Tests focus on parameter validation and endpoint routing since
the actual Navitia API calls are mocked.
"""

import os
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, settings
from c2corg_api.tests.routers import get_real_app


class TestNavitiaJourneysRouter(BaseTestCase):
    """Tests for /v2/navitia/journeys"""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def test_get_missing_from(self):
        """Missing 'from' parameter should return 400."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={
                'to': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 400

    def test_get_missing_to(self):
        """Missing 'to' parameter should return 400."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 400

    def test_get_missing_datetime(self):
        """Missing 'datetime' parameter should return 400."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={
                'from': '1.0;2.0',
                'to': '3.0;4.0',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 400

    def test_get_missing_datetime_represents(self):
        """Missing 'datetime_represents' parameter should return 400."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={'from': '1.0;2.0', 'to': '3.0;4.0', 'datetime': '20160101T120000'},
        )
        assert r.status_code == 400

    @patch.dict(os.environ, {'NAVITIA_API_KEY': ''})
    def test_get_missing_api_key(self):
        """Missing NAVITIA_API_KEY should return 500."""
        # Remove the key entirely
        env = os.environ.copy()
        env.pop('NAVITIA_API_KEY', None)
        with patch.dict(os.environ, env, clear=True):
            r = self.client.get(
                '/v2/navitia/journeys',
                params={
                    'from': '1.0;2.0',
                    'to': '3.0;4.0',
                    'datetime': '20160101T120000',
                    'datetime_represents': 'departure',
                },
            )
            assert r.status_code == 500

    @patch('c2corg_api.routers.navitia.navitia_get', return_value={'journeys': []})
    @patch.dict(os.environ, {'NAVITIA_API_KEY': 'test-key'})
    def test_get_success(self, mock_navitia_get):
        """Successful request proxies to navitia_get."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={
                'from': '1.0;2.0',
                'to': '3.0;4.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert 'journeys' in body
        mock_navitia_get.assert_called_once()

    @patch('c2corg_api.routers.navitia.navitia_get', return_value={'journeys': []})
    @patch.dict(os.environ, {'NAVITIA_API_KEY': 'test-key'})
    def test_get_with_optional_params(self, mock_navitia_get):
        """Optional params are forwarded."""
        r = self.client.get(
            '/v2/navitia/journeys',
            params={
                'from': '1.0;2.0',
                'to': '3.0;4.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_nb_transfers': '2',
            },
        )
        assert r.status_code == 200
        call_kwargs = mock_navitia_get.call_args
        params = call_kwargs.kwargs.get('params') or call_kwargs[1].get('params')
        assert params.get('walking_speed') == '1.12'
        assert params.get('max_nb_transfers') == '2'


class TestNavitiaReachableRouter(BaseTestCase):
    """Tests for reachable routes/waypoints start/result/progress endpoints."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def test_start_routes_missing_params(self):
        """Missing required parameters for journey reachable routes start."""
        r = self.client.get(
            '/v2/navitia/journeyreachableroutes/start',
            params={
                'from': '1.0;2.0'
                # missing datetime, datetime_represents, walking_speed,
                # max_walking_duration_to_pt
            },
        )
        assert r.status_code == 400

    def test_start_waypoints_missing_params(self):
        """Missing required parameters for journey reachable waypoints start."""
        r = self.client.get(
            '/v2/navitia/journeyreachablewaypoints/start', params={'from': '1.0;2.0'}
        )
        assert r.status_code == 400

    @patch(
        'c2corg_api.routers.navitia.start_job_background',
        return_value={'job_id': 'test-uuid'},
    )
    def test_start_routes_success(self, mock_start):
        """Successful start returns a job_id."""
        r = self.client.get(
            '/v2/navitia/journeyreachableroutes/start',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '900',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert 'job_id' in body

    @patch(
        'c2corg_api.routers.navitia.start_job_background',
        return_value={'job_id': 'test-uuid'},
    )
    def test_start_waypoints_success(self, mock_start):
        """Successful start returns a job_id."""
        r = self.client.get(
            '/v2/navitia/journeyreachablewaypoints/start',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '900',
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert 'job_id' in body

    @patch('c2corg_api.routers.navitia.read_result_from_redis')
    @patch('c2corg_api.routers.navitia.redis_client')
    def test_result_routes_unknown_job(self, mock_redis_client, mock_read):
        """Unknown job_id returns an error dict."""
        mock_read.return_value = {'error': 'unknown_job_id'}
        r = self.client.get('/v2/navitia/journeyreachableroutes/result/nonexistent')
        assert r.status_code == 200
        body = r.json()
        assert body.get('error') == 'unknown_job_id'

    @patch('c2corg_api.routers.navitia.read_result_from_redis')
    @patch('c2corg_api.routers.navitia.redis_client')
    def test_result_routes_running(self, mock_redis_client, mock_read):
        """Running job returns status running."""
        mock_read.return_value = {'status': 'running'}
        r = self.client.get('/v2/navitia/journeyreachableroutes/result/some-uuid')
        assert r.status_code == 200
        body = r.json()
        assert body.get('status') == 'running'

    @patch('c2corg_api.routers.navitia.read_result_from_redis')
    @patch('c2corg_api.routers.navitia.redis_client')
    def test_result_routes_done(self, mock_redis_client, mock_read):
        """Completed job returns result."""
        mock_read.return_value = {
            'status': 'done',
            'result': {'documents': [], 'total': 0},
        }
        r = self.client.get('/v2/navitia/journeyreachableroutes/result/some-uuid')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'done'
        assert body['result']['total'] == 0

    @patch('c2corg_api.routers.navitia.read_result_from_redis')
    @patch('c2corg_api.routers.navitia.redis_client')
    def test_result_waypoints_done(self, mock_redis_client, mock_read):
        """Completed waypoints job returns result."""
        mock_read.return_value = {
            'status': 'done',
            'result': {'documents': [], 'total': 0},
        }
        r = self.client.get('/v2/navitia/journeyreachablewaypoints/result/some-uuid')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'done'

    @patch('c2corg_api.routers.navitia.read_result_from_redis')
    @patch('c2corg_api.routers.navitia.redis_client')
    def test_result_routes_error(self, mock_redis_client, mock_read):
        """Error job returns error info."""
        mock_read.return_value = {'status': 'error', 'message': 'something broke'}
        r = self.client.get('/v2/navitia/journeyreachableroutes/result/some-uuid')
        assert r.status_code == 200
        body = r.json()
        assert body['status'] == 'error'
        assert body['message'] == 'something broke'

    def test_progress_routes_returns_sse(self):
        """Progress endpoint returns text/event-stream."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = [
            b'1',  # progress
            b'1',  # found
            b'0',  # not_found
            b'2',  # total
            b'done',  # status
        ]

        with patch('c2corg_api.routers.navitia.redis_client', return_value=mock_redis):
            r = self.client.get('/v2/navitia/journeyreachableroutes/progress/some-uuid')
            assert r.status_code == 200
            assert 'text/event-stream' in r.headers.get('content-type', '')


class TestNavitiaIsochroneRouter(BaseTestCase):
    """Tests for isochrone reachable routes/waypoints endpoints."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def test_isochrone_routes_missing_params(self):
        """Missing required parameters should return 400."""
        r = self.client.get(
            '/v2/navitia/isochronesreachableroutes',
            params={
                'from': '1.0;2.0'
                # missing datetime, datetime_represents, boundary_duration
            },
        )
        assert r.status_code == 400

    def test_isochrone_waypoints_missing_params(self):
        """Missing required parameters should return 400."""
        r = self.client.get(
            '/v2/navitia/isochronesreachablewaypoints',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                # missing datetime_represents, boundary_duration
            },
        )
        assert r.status_code == 400

    def test_isochrone_routes_missing_boundary_duration(self):
        """Missing 'boundary_duration' should return 400."""
        r = self.client.get(
            '/v2/navitia/isochronesreachableroutes',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 400

    def test_isochrone_waypoints_missing_boundary_duration(self):
        """Missing 'boundary_duration' should return 400."""
        r = self.client.get(
            '/v2/navitia/isochronesreachablewaypoints',
            params={
                'from': '1.0;2.0',
                'datetime': '20160101T120000',
                'datetime_represents': 'departure',
            },
        )
        assert r.status_code == 400
