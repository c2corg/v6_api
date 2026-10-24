import json
import os
from datetime import datetime, time
from unittest import mock
from unittest.mock import call

import pytest
import redis
import requests
from dotenv import load_dotenv
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnauthorized,
)
from shapely.geometry import Polygon

from c2corg_api.models.area import Area
from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route, RouteLocale, schema_route
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import BaseTestCase
from c2corg_api.views import to_json_dict
from c2corg_api.views.coverage import (
    clear_coverages_cache,
    get_coverage,
    get_coverages,
)
from c2corg_api.views.navitia import (
    BASE_URL,
    MAX_ROUTE_THRESHOLD,
    MAX_TRIP_DURATION,
    MIN_TRIP_DURATION,
    _is_one_way_route,
    _resolve_hiking_duration_seconds,
    _sort_targets_by_distance,
    _store_job_progress,
    best_round_trip_result,
    compute_journey_reachable_routes,
    compute_journey_reachable_waypoints,
    compute_round_trip_reachable_routes,
    compute_round_trip_reachable_waypoints,
    extract_isochrone_params,
    extract_journey_params,
    extract_meta_params,
    get_cached_isochrone_pair,
    get_cached_transport_document_ids,
    get_job_status,
    get_navitia_isochrone,
    get_navitia_isochrone_pair,
    handle_navitia_response,
    is_wp_in_isochrone,
    is_wp_journey_reachable,
    is_wp_round_trip_reachable,
    navitia_get,
    parse_transport_params,
    progress_stream,
    read_result_from_redis,
    redis_client,
    start_job_background,
)

# load .env into os.environ (call once)
load_dotenv()

NAVITIA_GET_PATH = 'c2corg_api.views.navitia.navitia_get'
NAVITIA_REDIS_CLIENT_PATH = 'c2corg_api.views.navitia.redis_client'
NAVITIA_KEY = os.getenv('NAVITIA_API_KEY', 'test-key')


class FakeCache:
    """in-memory replacement of the redis client used as a cache"""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value


class TestNavitiaRestParams(BaseTestCase):
    # /navitia/journeys endpoint
    def test_journey_missing_required_params(self):
        with mock.patch.dict(os.environ, {'NAVITIA_API_KEY': NAVITIA_KEY}):
            # missing to
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&datetime=20260116T115100&datetime_represents=departure',
                status=400,
            )
            # missing from
            self.app.get(
                '/navitia/journeys?to=5.0;45.0&datetime=20260116T115100&datetime_represents=departure',
                status=400,
            )
            # missing datetime
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime_represents=departure',
                status=400,
            )
            # missing datetime_represents
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100',
                status=400,
            )

    def test_journey_invalid_coordinate_format(self):
        with mock.patch.dict(os.environ, {'NAVITIA_API_KEY': NAVITIA_KEY}):
            # 200 OK is expected since wrong values for from or to parameter
            # are not considered as bad request but as 404 not found
            # invalid 'from'
            self.app.get(
                '/navitia/journeys?from=invalid&to=5.1;45.1&datetime=20260116T115100&datetime_represents=departure',
                status=200,
            )
            # invalid 'to'
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=notcoords&datetime=20260116T115100&datetime_represents=departure',
                status=200,
            )

    def test_journey_invalid_datetime(self):
        with mock.patch.dict(os.environ, {'NAVITIA_API_KEY': NAVITIA_KEY}):
            # invalid datetime
            # should be status = 500 but
            # conftest mocks every call to return 200 OK.
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=invalid&datetime_represents=departure',
                status=200,
            )

    def test_journey_invalid_datetime_represents(self):
        with mock.patch.dict(os.environ, {'NAVITIA_API_KEY': NAVITIA_KEY}):
            # invalid datetime_represents
            # should be status = 500 but
            # conftest mocks every call to return 200 OK.
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100&datetime_represents=invalid',
                status=200,
            )

    def test_journey_missing_api_key(self):
        # ensure NAVITIA_API_KEY not set in env
        with mock.patch.dict(os.environ, {}, clear=True):
            self.app.get(
                '/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100&datetime_represents=departure',
                status=500,
            )

    def test_navitia_journey_success(self):
        # datetime parameter is today's date 08:00
        # so that we don't face the datetime out of production error
        dt = datetime.combine(datetime.today().date(), time(hour=8, minute=0, second=0))
        dt_str = dt.strftime('%Y%m%dT%H%M%S')

        with mock.patch.dict(os.environ, {'NAVITIA_API_KEY': NAVITIA_KEY}):
            self.app.get(
                f'/navitia/journeys?'
                f'from=5.7357819%3B45.1875602&'
                f'to=5.166955054538887%3B45.07757475794273&'
                f'datetime={dt_str}&'
                f'datetime_represents=departure&'
                f'walking_speed=1.12&'
                f'max_walking_duration_to_pt=4464&'
                f'min_nb_journeys=3&',
                status=200,
            )

    # individual job handling functions
    def test_get_redis_client(self):
        assert redis_client() is not None

    def test_start_job(self):
        with mock.patch(NAVITIA_REDIS_CLIENT_PATH) as mock_redis_client:
            mock_r = mock_redis_client.return_value

            result = start_job_background(lambda *_: None, request={'a': 1})

            job_id = result['job_id']

            mock_r.set.assert_any_call(f'job:{job_id}:progress', 0)
            mock_r.set.assert_any_call(f'job:{job_id}:status', 'running')

    def test_store_job_progress(self):
        with mock.patch(NAVITIA_REDIS_CLIENT_PATH) as mock_redis_client:
            mock_r = mock_redis_client.return_value
            job_id = 'job-123'

            _store_job_progress(mock_r, job_id, count=5, found=3, not_found=2)

            mock_r.set.assert_any_call(f'job:{job_id}:progress', 5)
            mock_r.set.assert_any_call(f'job:{job_id}:found', 3)
            mock_r.set.assert_any_call(f'job:{job_id}:not_found', 2)

            mock_r.publish.assert_any_call(f'job:{job_id}:events', 'progress:5')
            mock_r.publish.assert_any_call(f'job:{job_id}:events', 'found:3')
            mock_r.publish.assert_any_call(f'job:{job_id}:events', 'not_found:2')

    def test_get_job_status(self):
        r = mock.Mock()
        job_id = 'job-123'

        r.get.return_value = b'running'

        status, payload = get_job_status(r, job_id)

        r.get.assert_called_once_with(f'job:{job_id}:status')
        assert status == 'running'
        assert payload == 'running'

    def test_get_job_status_unknown_job(self):
        r = mock.Mock()
        job_id = 'job-123'

        r.get.return_value = None

        status, payload = get_job_status(r, job_id)

        r.get.assert_called_once_with(f'job:{job_id}:status')
        assert status is None
        assert payload == {'error': 'unknown_job_id'}

    def test_read_result_from_redis_unknown_status(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f'job:{job_id}:status':
                return b'abcd'

        r = mock.Mock()
        job_id = 'job-123'

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f'job:{job_id}:status')
        assert response == {'error': 'unknown_status', 'status': 'abcd'}

    def test_read_result_from_redis_job_error(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f'job:{job_id}:status':
                return b'error'
            if args[0] == f'job:{job_id}:error':
                return b'fake error message'

        r = mock.Mock()
        job_id = 'job-123'

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls(
            [call(f'job:{job_id}:status'), call(f'job:{job_id}:error')]
        )
        assert response == {'status': 'error', 'message': 'fake error message'}

    def test_read_result_from_redis_unknown_job(self):
        r = mock.Mock()
        job_id = 'job-123'

        r.get.return_value = None

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f'job:{job_id}:status')
        assert response == {'error': 'unknown_job_id'}

    def test_read_result_from_redis_job_running(self):
        r = mock.Mock()
        job_id = 'job-123'

        r.get.return_value = b'running'

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f'job:{job_id}:status')
        assert response == {'status': 'running'}

    def test_read_result_from_redis_job_done_no_data(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f'job:{job_id}:status':
                return b'done'
            if args[0] == f'job:{job_id}:result':
                return None

        r = mock.Mock()
        job_id = 'job-123'

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls(
            [call(f'job:{job_id}:status'), call(f'job:{job_id}:result')]
        )
        assert response == {'status': 'error', 'message': 'missing_result'}

    def test_read_result_from_redis_job_done_success(self):
        def error_side_effect(*args, **kwargs):
            r1 = to_json_dict(
                Route(activities=['hiking', 'rock_climbing']), schema_route
            )
            r2 = to_json_dict(
                Route(activities=['slacklining', 'rock_climbing']), schema_route
            )
            routes = [r1, r2]
            if args[0] == f'job:{job_id}:status':
                return b'done'
            if args[0] == f'job:{job_id}:result':
                return json.dumps({'documents': routes, 'total': len(routes)})

        r1 = to_json_dict(Route(activities=['hiking', 'rock_climbing']), schema_route)
        r2 = to_json_dict(
            Route(activities=['slacklining', 'rock_climbing']), schema_route
        )
        routes = [r1, r2]

        r = mock.Mock()
        job_id = 'job-123'

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls(
            [call(f'job:{job_id}:status'), call(f'job:{job_id}:result')]
        )
        assert response == {
            'status': 'done',
            'result': {'documents': routes, 'total': len(routes)},
        }

    def test_progress_stream_done(self):
        r = mock.Mock()

        # Simulate Redis responses in call order
        r.get.side_effect = [
            b'10',  # progress
            b'7',  # found
            b'3',  # not_found
            b'10',  # total
            b'done',  # status → terminates loop
        ]

        with mock.patch('c2corg_api.views.navitia.time.sleep'):
            gen = progress_stream(r, job_id='job-123')

            first = next(gen)
            second = next(gen)

        payload = json.loads(first.decode().replace('data: ', '').strip())

        assert payload == {'progress': 10, 'total': 10, 'found': 7, 'not_found': 3}

        assert second == b'event: done\ndata: done\n\n'

    def test_progress_stream_init(self):
        r = mock.Mock()
        r.get.side_effect = [
            None,
            None,
            None,
            None,  # progress fields
            b'running',
        ]

        with mock.patch('c2corg_api.views.navitia.time.sleep'):
            gen = progress_stream(r, job_id='123')
            output = next(gen)

        payload = json.loads(output.decode().replace('data: ', '').strip())

        assert payload == {'progress': 0, 'total': 0, 'found': 0, 'not_found': 0}

    def test_progress_stream_error(self):
        r = mock.Mock()
        r.get.side_effect = [
            b'5',  # progress
            b'3',  # found
            b'2',  # not_found
            b'10',  # total
            b'error',  # status → terminates loop
            b"{'msg': 'error message'}",
        ]

        with mock.patch('c2corg_api.views.navitia.time.sleep'):
            gen = progress_stream(r, job_id='123')
            next(gen)
            second = next(gen)

        assert second.startswith(b'event: error')
        assert b'"msg": "error message"' in second

    # /navitia/journeyreachableroutes endpoints (includes job handling)
    # /navitia/journeyreachableroutes/start endpoint
    # /navitia/journeyreachablewaypoints/start endpoint
    def test_navitia_journeyreachabledocs_start(self, subtests):
        test_cases = [
            ('/navitia/journeyreachableroutes', compute_journey_reachable_routes),
            ('/navitia/journeyreachablewaypoints', compute_journey_reachable_waypoints),
        ]

        for base_url, func in test_cases:
            with subtests.test(base_url=base_url, func=func):
                with mock.patch(
                    'c2corg_api.views.navitia.start_job_background'
                ) as mock_start:
                    mock_start.return_value = 'job-123'

                    # call with any parameters that
                    # passes the function validate_journey_params,
                    # as the result will anyway be mocked
                    response = self.app.get(
                        (
                            base_url + '/start?'
                            'datetime=20260122T143500&'
                            'datetime_represents=departure&'
                            'from=5.677893899999996%3B45.1929973&'
                            'walking_speed=1.12&'
                            'max_walking_duration_to_pt=4464'
                        ),
                        status=200,
                    )
                    assert json.loads(response.body.decode()) == 'job-123'
                    mock_start.assert_called_once_with(func, mock.ANY)

    def test_navitia_journeyreachabledocs_start_missing_params(self, subtests):
        base_urls = [
            '/navitia/journeyreachableroutes',
            '/navitia/journeyreachablewaypoints',
        ]

        for base_url in base_urls:
            with subtests.test(base_url=base_url):
                # missing datetime
                self.app.get(
                    base_url
                    + '/start?&datetime_represents=departure&from=5.677893899999996%3B45.1929973&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400,
                )

                # missing datetime represents
                self.app.get(
                    base_url
                    + '/start?datetime=20260122T143500&from=5.677893899999996%3B45.1929973&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400,
                )

                # missing from
                self.app.get(
                    base_url
                    + '/start?datetime=20260122T143500&datetime_represents=departure&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400,
                )

                # missing walking speed
                self.app.get(
                    base_url
                    + '/start?datetime=20260122T143500&datetime_represents=departure&from=5.677893899999996%3B45.1929973&max_walking_duration_to_pt=4464',  # noqa
                    status=400,
                )

                # missing max_walking_duration_to_pt
                self.app.get(
                    base_url
                    + '/start?datetime=20260122T143500&datetime_represents=departure&from=5.677893899999996%3B45.1929973&walking_speed=1.12',  # noqa
                    status=400,
                )

    # /navitia/journeyreachableroutes/progress endpoint
    # /navitia/journeyreachablewaypoints/progress endpoint
    def test_navitia_journeyreachabledocs_progress(self, subtests):
        urls = [
            '/navitia/journeyreachableroutes/progress/job-123',
            '/navitia/journeyreachablewaypoints/progress/job-123',
        ]

        for url in urls:
            with subtests.test(url=url):
                fake_events = [
                    b'data: %s\n\n'
                    % json.dumps(
                        {'progress': 0, 'total': 10, 'found': 0, 'not_found': 0}
                    ).encode('utf-8'),
                    b'data: %s\n\n'
                    % json.dumps(
                        {'progress': 5, 'total': 10, 'found': 4, 'not_found': 1}
                    ).encode('utf-8'),
                    b'data: %s\n\n'
                    % json.dumps(
                        {'progress': 9, 'total': 10, 'found': 6, 'not_found': 3}
                    ).encode('utf-8'),
                ]

                def fake_progress_stream(redis, job_id):
                    assert job_id == 'job-123'
                    for event in fake_events:
                        yield event

                with (
                    mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis,
                    mock.patch(
                        'c2corg_api.views.navitia.progress_stream',
                        side_effect=fake_progress_stream,
                    ) as mock_progress,
                ):
                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(url, status=200)

                    # Content type should be SSE
                    assert response.content_type == 'text/event-stream'
                    body = response.body
                    assert body == b''.join(fake_events)

                    mock_progress.assert_called_once_with(
                        mock_redis.return_value, 'job-123'
                    )

    # /navitia/journeyreachableroutes/result endpoint
    # /navitia/journeyreachablewaypoints/result endpoint
    def test_navitia_journeyreachabledocs_result(self, subtests):
        urls = [
            '/navitia/journeyreachableroutes/result/job-123',
            '/navitia/journeyreachablewaypoints/result/job-123',
        ]

        for url in urls:
            with subtests.test(url=url):

                def fake_read_result(redis, job_id):
                    assert job_id == 'job-123'
                    return {'status': 'error', 'message': 'missing_result'}

                with (
                    mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis,
                    mock.patch(
                        'c2corg_api.views.navitia.read_result_from_redis',
                        side_effect=fake_read_result,
                    ) as mock_read_result,
                ):
                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(url, status=200)

                    body = response.body
                    assert json.loads(body.decode()) == {
                        'status': 'error',
                        'message': 'missing_result',
                    }

                    mock_read_result.assert_called_once_with(
                        mock_redis.return_value, 'job-123'
                    )

    # /navitia/isochronereachableroutes endpoint
    def test_navitia_isochronereachableroutes(self):
        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_isochrone_params'
            ) as mock_extract_isochrone_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_route_query_with_waypoints'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.collect_waypoints_from_results'
            ) as mock_collect_wp,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone'
            ) as mock_get_iso,
            mock.patch('c2corg_api.views.navitia.is_wp_in_isochrone') as mock_is_in_iso,
            mock.patch('c2corg_api.views.navitia.to_json_dict') as mock_to_json,
        ):
            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }

            mock_extract_isochrone_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'boundary_duration[]': 3600,  # 1 hour
            }

            mock_query = mock.Mock()
            r1 = Route(document_id='1', activities=['hiking'])
            r2 = Route(document_id='2', activities=['slacklining'])
            results = [
                (r1, [{'document_id': '1'}], [{'document_id': '1'}]),
                (r2, [{'document_id': '1'}], [{'document_id': '2'}]),
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
                    ),
                )
            }
            mock_collect_wp.return_value = [
                Waypoint(document_id='1', waypoint_type='access'),
                Waypoint(document_id='2', waypoint_type='access'),
            ]

            # any polygon
            mock_get_iso.return_value = {
                'isochrones': [
                    {
                        'geojson': {
                            'type': 'Polygon',
                            'coordinates': [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        }
                    }
                ]
            }

            def is_in_iso_side_effect(wp_json, geom):
                if wp_json['document_id'] == '1':
                    return True
                return False

            mock_is_in_iso.side_effect = is_in_iso_side_effect

            def to_json_side_effect(obj, schema=None, full=False):
                doc_id = getattr(obj, 'document_id', None)
                return {'document_id': doc_id}

            mock_to_json.side_effect = to_json_side_effect

            result = self.app.get(
                '/navitia/isochronesreachableroutes?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600',
                status=200,
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'
            assert result_data['isochron_geom'] == {
                'type': 'Polygon',
                'coordinates': [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
            }

    def test_navitia_isochronereachableroutes_no_result(self):
        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_isochrone_params'
            ) as mock_extract_isochrone_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_route_query_with_waypoints'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.collect_waypoints_from_results'
            ) as mock_collect_wp,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone'
            ) as mock_get_iso,
        ):
            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }

            mock_extract_isochrone_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'boundary_duration[]': 3600,  # 1 hour
            }

            mock_query = mock.Mock()
            r1 = Route(document_id='1', activities=['hiking'])
            r2 = Route(document_id='2', activities=['slacklining'])
            results = [
                (r1, [{'document_id': '1'}], [{'document_id': '1'}]),
                (r2, [{'document_id': '1'}], [{'document_id': '2'}]),
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
                    ),
                )
            }
            mock_collect_wp.return_value = [
                Waypoint(document_id='1', waypoint_type='access'),
                Waypoint(document_id='2', waypoint_type='access'),
            ]

            # any polygon
            mock_get_iso.return_value = {'isochrones': []}

            result = self.app.get(
                '/navitia/isochronesreachableroutes?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600',
                status=200,
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 0
            assert result_data['isochron_geom'] == ''

    # /navitia/isochronereachablewaypoints endpoint
    def test_navitia_isochronereachablewaypoints(self):
        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_isochrone_params'
            ) as mock_extract_isochrone_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_waypoints_query'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone'
            ) as mock_get_iso,
            mock.patch('c2corg_api.views.navitia.is_wp_in_isochrone') as mock_is_in_iso,
            mock.patch('c2corg_api.views.navitia.to_json_dict') as mock_to_json,
        ):
            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }

            mock_extract_isochrone_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'boundary_duration[]': 3600,  # 1 hour
            }

            mock_query = mock.Mock()
            results = [
                (
                    Waypoint(document_id='1', waypoint_type='access'),
                    [{'document_id': '1'}],
                ),
                (
                    Waypoint(document_id='2', waypoint_type='access'),
                    [{'document_id': '1'}],
                ),
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
                    ),
                )
            }

            # any polygon
            mock_get_iso.return_value = {
                'isochrones': [
                    {
                        'geojson': {
                            'type': 'Polygon',
                            'coordinates': [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        }
                    }
                ]
            }

            def is_in_iso_side_effect(wp_json, geom):
                if wp_json['document_id'] == '1':
                    return True
                return False

            mock_is_in_iso.side_effect = is_in_iso_side_effect

            def to_json_side_effect(obj, schema=None, full=False):
                doc_id = getattr(obj, 'document_id', None)
                return {'document_id': doc_id}

            mock_to_json.side_effect = to_json_side_effect

            result = self.app.get(
                '/navitia/isochronesreachablewaypoints?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600',
                status=200,
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'
            assert result_data['isochron_geom'] == {
                'type': 'Polygon',
                'coordinates': [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
            }

    def test_navitia_isochronereachablewaypoints_no_result(self):
        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_isochrone_params'
            ) as mock_extract_isochrone_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_waypoints_query'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone'
            ) as mock_get_iso,
        ):
            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }

            mock_extract_isochrone_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'boundary_duration[]': 3600,  # 1 hour
            }

            mock_query = mock.Mock()
            results = [
                (
                    Waypoint(document_id='1', waypoint_type='access'),
                    [{'document_id': '1'}],
                ),
                (
                    Waypoint(document_id='2', waypoint_type='access'),
                    [{'document_id': '2'}],
                ),
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
                    ),
                )
            }

            # any polygon
            mock_get_iso.return_value = {'isochrones': []}

            result = self.app.get(
                '/navitia/isochronesreachablewaypoints?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600',
                status=200,
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 0
            assert result_data['isochron_geom'] == ''

    # individual business functions used in routes
    def test_compute_journey_reachable_routes(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_route_query_with_waypoints'
            ) as mock_build_reachable_route_query_with_waypoints,
            mock.patch(
                'c2corg_api.views.navitia.collect_waypoints_from_results'
            ) as mock_collect_wp,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.extract_journey_params'
            ) as mock_extract_journey_params,
            mock.patch(
                'c2corg_api.views.navitia.is_wp_journey_reachable'
            ) as mock_is_reachable,
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }
            mock_extract_journey_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '4464',
                'to': '5.166955054538887%3B45.07757475794273',
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = [
                (
                    Route(activities=['hiking', 'rock_climbing']),
                    [{'document_id': '1'}],
                    [{'document_id': '1'}],
                ),
                (
                    Route(activities=['hiking']),
                    [{'document_id': '1'}],
                    [{'document_id': '2'}],
                ),
            ]
            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query,
                len(mock_query.all.return_value),
            )

            # --- mock areas / waypoints ---
            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
                    ),
                )
            }

            mock_collect_wp.return_value = [
                Waypoint(waypoint_type='access', document_id='1'),
                Waypoint(waypoint_type='access', document_id='2'),
            ]

            # --- mock Navitia reachability ---
            # Simulate wp1 reachable, wp2 not reachable
            def is_reachable_side_effect(wp_json, journey_params):
                return wp_json['document_id'] == '1'

            mock_is_reachable.side_effect = is_reachable_side_effect

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            # --- call function ---
            request = mock.Mock()
            request.GET = {}
            compute_journey_reachable_routes(job_id, request)

            # --- assertions ---
            # Check total
            mock_redis.set.assert_any_call(f'job:{job_id}:total', 2)

            # Check Redis was called with correct job status
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            # Get the stored result from Redis
            result_json = mock_redis.set.call_args_list
            result_json = next(
                call[0][1]
                for call in result_json
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)
            routes = result_data['documents']

            assert len(routes) == 1
            assert routes[0]['activities'] == ['hiking', 'rock_climbing']

    def test_compute_journey_reachable_routes_no_results(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_route_query_with_waypoints'
            ) as mock_build_reachable_route_query_with_waypoints,
            mock.patch(
                'c2corg_api.views.navitia.collect_waypoints_from_results'
            ) as mock_collect_wp,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.extract_journey_params'
            ) as mock_extract_journey_params,
            mock.patch(
                'c2corg_api.views.navitia.is_wp_journey_reachable'
            ) as mock_is_reachable,  # noqa
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }
            mock_extract_journey_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '4464',
                'to': '5.166955054538887%3B45.07757475794273',
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = []

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query,
                len(mock_query.all.return_value),
            )

            # --- mock areas / waypoints ---
            mock_collect_areas.return_value = {}

            mock_collect_wp.return_value = []

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            # --- call function ---
            request = mock.Mock()
            request.GET = {}
            compute_journey_reachable_routes(job_id, request)

            # --- assertions ---
            # Check total
            mock_redis.set.assert_any_call(f'job:{job_id}:total', 0)

            # Check Redis was called with correct job status
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            # Get the stored result from Redis
            result_json = mock_redis.set.call_args_list
            result_json = next(
                call[0][1]
                for call in result_json
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)
            routes = result_data['documents']

            assert len(routes) == 0

    def test_compute_journey_reachable_routes_above_threshold(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_route_query_with_waypoints'
            ) as mock_build_reachable_route_query_with_waypoints,
            mock.patch(
                'c2corg_api.views.navitia.collect_waypoints_from_results'
            ) as mock_collect_wp,  # noqa
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,  # noqa
            mock.patch(
                'c2corg_api.views.navitia.extract_journey_params'
            ) as mock_extract_journey_params,
            mock.patch(
                'c2corg_api.views.navitia.is_wp_journey_reachable'
            ) as mock_is_reachable,  # noqa
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }
            mock_extract_journey_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '4464',
                'to': '5.166955054538887%3B45.07757475794273',
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = [
                (Route(), [], []) for _ in range(MAX_ROUTE_THRESHOLD + 1)
            ]

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query,
                len(mock_query.all.return_value),
            )

            request = mock.Mock()
            request.GET = {}

            compute_journey_reachable_routes(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')

            mock_redis.set.assert_any_call(
                f'job:{job_id}:error',
                "Couldn't proceed with computation : Too much routes found.",
            )

            # Ensure no result was written
            assert not any(
                call[0][0] == f'job:{job_id}:result'
                for call in mock_redis.set.call_args_list
            )

    def test_compute_journey_reachable_waypoints(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_journey_params'
            ) as mock_extract_journey_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_waypoints_query'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.is_wp_journey_reachable'
            ) as mock_is_reachable,
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            # mock meta/journey params
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }
            mock_extract_journey_params.return_value = {
                'from': '5.7357819%3B45.1875602',
                'datetime': '20260116T115100',
                'datetime_represents': 'departure',
                'walking_speed': '1.12',
                'max_walking_duration_to_pt': '4464',
                'to': '5.166955054538887%3B45.07757475794273',
            }

            # mock query results
            mock_query = mock.Mock()
            # list of tuples: (waypoint, areas)
            mock_query.all.return_value = [
                (
                    Waypoint(document_id='1', waypoint_type='access'),
                    [{'document_id': '1'}],
                ),
                (
                    Waypoint(document_id='2', waypoint_type='access'),
                    [{'document_id': '1'}],
                ),
            ]
            mock_build_query.return_value = (
                mock_query,
                len(mock_query.all.return_value),
            )

            # mock areas
            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa: E501
                    ),
                )
            }

            # mock reachability
            def is_reachable_side_effect(wp_json, journey_params):
                # only first waypoint reachable
                return wp_json['document_id'] == '1'

            mock_is_reachable.side_effect = is_reachable_side_effect

            # mock Redis
            mock_redis = mock_redis_client.return_value

            # call function
            request = mock.Mock()
            request.GET = {'a': '1'}  # single area filter
            compute_journey_reachable_waypoints(job_id, request)

            # assertions
            # total waypoints queried
            mock_redis.set.assert_any_call(f'job:{job_id}:total', 2)

            # check final status
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            # result contains only reachable waypoint
            result_json = next(
                call[0][1]
                for call in mock_redis.set.call_args_list
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)
            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'

    def test_compute_journey_reachable_waypoints_no_results(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.extract_meta_params'
            ) as mock_extract_meta_params,
            mock.patch(
                'c2corg_api.views.navitia.extract_journey_params'
            ) as mock_extract_journey_params,
            mock.patch(
                'c2corg_api.views.navitia.build_reachable_waypoints_query'
            ) as mock_build_query,
            mock.patch(
                'c2corg_api.views.navitia.collect_areas_from_results'
            ) as mock_collect_areas,
            mock.patch(
                'c2corg_api.views.navitia.is_wp_journey_reachable'
            ) as mock_is_reachable,  # noqa
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            mock_extract_meta_params.return_value = {
                'offset': 0,
                'limit': 100,
                'lang': 'fr',
            }
            mock_extract_journey_params.return_value = {'from': '...', 'to': '...'}

            mock_query = mock.Mock()
            mock_query.all.return_value = []
            mock_build_query.return_value = (mock_query, 0)

            mock_collect_areas.return_value = {}

            mock_redis = mock_redis_client.return_value

            request = mock.Mock()

            # only one area
            request.GET = {'a': '1'}
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:total', 0)
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            # result empty
            result_json = next(
                call[0][1]
                for call in mock_redis.set.call_args_list
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)
            assert result_data['total'] == 0
            assert result_data['documents'] == []

    def test_compute_journey_reachable_waypoints_missing_area(self):
        job_id = 'job-123'

        with mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client:
            mock_redis = mock_redis_client.return_value
            request = mock.Mock()
            # no areas
            request.GET = {}
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')
            mock_redis.set.assert_any_call(
                f'job:{job_id}:error', 'Missing filter : area is required'
            )

    def test_compute_journey_reachable_waypoints_multiple_areas(self):
        job_id = 'job-123'

        with mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client:
            mock_redis = mock_redis_client.return_value
            request = mock.Mock()
            request.GET = {'a': '1,2'}  # multiple areas
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')
            mock_redis.set.assert_any_call(
                f'job:{job_id}:error', 'Only one filtering area is allowed'
            )

    def test_handle_navitia_response_success(self):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {'data': 'some_data'}

        result = handle_navitia_response(mock_response)
        assert result == {'data': 'some_data'}

    def test_handle_navitia_response_401(self):
        mock_response = mock.Mock()
        mock_response.status_code = 401

        with pytest.raises(HTTPUnauthorized):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_400(self):
        mock_response = mock.Mock()
        mock_response.status_code = 400

        with pytest.raises(HTTPBadRequest):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_404_no_journey(self):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {'error': {'id': 'no_solution'}}

        with pytest.raises(HTTPNotFound):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_404_other_error(self):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {'error': {'id': 'unknown_object'}}
        with pytest.raises(HTTPNotFound):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_other_error(self):
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.ok = False

        with pytest.raises(HTTPInternalServerError):
            handle_navitia_response(mock_response)

    def test_navitia_get_normal_operation(self):
        with mock.patch('requests.get') as mock_get:
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.ok = True
            mock_response.json.return_value = {'data': 'some_data'}
            mock_get.return_value = mock_response

            result = navitia_get(BASE_URL)
            assert result == {'data': 'some_data'}

    def test_navitia_get_timeout(self):
        with mock.patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout

            with pytest.raises(HTTPInternalServerError):
                navitia_get(BASE_URL)

    def test_navitia_get_other_request_exception(self):
        with mock.patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException(
                'An error occurred'
            )

            with pytest.raises(HTTPInternalServerError):
                navitia_get(BASE_URL)

    def test_navitia_extract_meta_params_no_lang(self):
        mock_request = mock.Mock()
        mock_request.validated = {}
        result = extract_meta_params(mock_request)
        assert result == {'offset': 0, 'limit': 2000, 'lang': None}

    def test_navitia_extract_meta_params_with_lang(self):
        mock_request = mock.Mock()
        mock_request.validated = {
            'limit': 50,
            'lang': 'fr',
        }
        result = extract_meta_params(mock_request)
        assert result == {'offset': 0, 'limit': 2000, 'lang': 'fr'}

    def test_navitia_extract_journey_params(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
        }
        result = extract_journey_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
            'to': '',
        }

    def test_navitia_extract_isochrone_params_upper_bounded(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(MAX_TRIP_DURATION * 60 + 10000),
            'datetime_represents': 'departure',
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MAX_TRIP_DURATION * 60,
            'datetime_represents': 'departure',
        }

    def test_navitia_extract_isochrone_params_lower_bounded(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(MIN_TRIP_DURATION * 60 - 10000),
            'datetime_represents': 'departure',
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MIN_TRIP_DURATION * 60,
            'datetime_represents': 'departure',
        }

    def test_navitia_extract_isochrone_params(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(
                int((MAX_TRIP_DURATION * 60 + MIN_TRIP_DURATION * 60) / 2)
            ),
            'datetime_represents': 'departure',
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': int(
                (MAX_TRIP_DURATION * 60 + MIN_TRIP_DURATION * 60) / 2
            ),
            'datetime_represents': 'departure',
        }

    def test_navitia_extract_isochrone_params_multiple_boundaries(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': '4000, 8000, 12000',
            'datetime_represents': 'departure',
        }
        # default value is MAX_TRIP_DURATION
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MAX_TRIP_DURATION * 60,
            'datetime_represents': 'departure',
        }

    def test_is_wp_in_isochrone(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            'geom': json.dumps(
                {'type': 'Point', 'coordinates': [665870.779788, 5653070.161742]}
            )
        }

        # Create a mock isochrone geometry
        isochrone_geom = Polygon([(1.0, 40.0), (1.0, 50.0), (10.0, 50.0), (10.0, 40.0)])

        result = is_wp_in_isochrone(mock_wp, isochrone_geom)

        assert result

    def test_is_wp_not_in_isochrone(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            'geom': json.dumps({'type': 'Point', 'coordinates': [0, 0]})
        }

        # Create a mock isochrone geometry
        isochrone_geom = Polygon([(4.0, 24.0), (4.0, 26.0), (6.0, 26.0), (6.0, 24.0)])

        result = is_wp_in_isochrone(mock_wp, isochrone_geom)

        assert not result

    def test_get_navitia_isochrone(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = '5;45'
        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            get_navitia_isochrone(mock_isochrone_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + '/coverage/fr-se/isochrones',
                params=mock_isochrone_params,
                headers={'Authorization': NAVITIA_KEY},
            )

    def test_get_navitia_isochrone_missing_api_key(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = '5;45'
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPInternalServerError):
                get_navitia_isochrone(mock_isochrone_params)

    def test_get_navitia_isochrone_no_source_coverage(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = '5;45'
        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
        ):
            mock_get_coverage.return_value = None
            with pytest.raises(HTTPInternalServerError):
                get_navitia_isochrone(mock_isochrone_params)

    def test_is_wp_journey_reachable(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            'geom': json.dumps({'type': 'Point', 'coordinates': [0, 0]})
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': '5.7357819%3B45.1875602',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
            'to': '',
        }

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            is_wp_journey_reachable(mock_wp, mock_journey_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + '/coverage/fr-se/journeys',
                params=mock_journey_params,
                headers={'Authorization': NAVITIA_KEY},
            )

    def test_is_wp_journey_reachable_missing_api_key(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            'geom': json.dumps({'type': 'Point', 'coordinates': [0, 0]})
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': '5.7357819%3B45.1875602',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
            'to': '',
        }

        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPInternalServerError):
                is_wp_journey_reachable(mock_wp, mock_journey_params)

    def test_is_wp_journey_reachable_no_destination_coverage(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            'geom': json.dumps({'type': 'Point', 'coordinates': [0, 0]})
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': '5.7357819%3B45.1875602',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
            'to': '',
        }

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = None
            is_wp_journey_reachable(mock_wp, mock_journey_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + '/journeys',
                params=mock_journey_params,
                headers={'Authorization': NAVITIA_KEY},
            )

    # get_navitia_isochrone_pair
    def test_get_navitia_isochrone_pair_both_found(self):
        aller_geojson = {
            'type': 'Polygon',
            'coordinates': [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]],
        }
        retour_geojson = {
            'type': 'Polygon',
            'coordinates': [[[1, 1], [1, 3], [3, 3], [3, 1], [1, 1]]],
        }

        responses = [
            {'isochrones': [{'geojson': aller_geojson}]},
            {'isochrones': [{'geojson': retour_geojson}]},
        ]

        with mock.patch(
            'c2corg_api.views.navitia.get_navitia_isochrone', side_effect=responses
        ) as mock_get_iso:
            result = get_navitia_isochrone_pair(
                '5.1;45.1', '2026-01-16', '08:00', '18:00'
            )

        assert result['aller_geom'] is not None
        assert result['retour_geom'] is not None
        assert result['intersection_geom'] is not None
        assert result['intersection_geom']['type'] == 'Polygon'

        aller_call_params = mock_get_iso.call_args_list[0][0][0]
        retour_call_params = mock_get_iso.call_args_list[1][0][0]

        assert aller_call_params['from'] == '5.1;45.1'
        assert aller_call_params['datetime'] == '20260116T080000'
        assert aller_call_params['datetime_represents'] == 'departure'
        # window (600 min) is above MAX_TRIP_DURATION, so it is clamped
        assert aller_call_params['boundary_duration[]'] == MAX_TRIP_DURATION * 60

        assert retour_call_params['to'] == '5.1;45.1'
        assert retour_call_params['datetime'] == '20260116T180000'
        assert retour_call_params['datetime_represents'] == 'arrival'
        assert retour_call_params['boundary_duration[]'] == MAX_TRIP_DURATION * 60

    def test_get_navitia_isochrone_pair_retour_empty(self):
        aller_geojson = {
            'type': 'Polygon',
            'coordinates': [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]],
        }

        responses = [
            {'isochrones': [{'geojson': aller_geojson}]},
            {'isochrones': []},
        ]

        with mock.patch(
            'c2corg_api.views.navitia.get_navitia_isochrone', side_effect=responses
        ):
            result = get_navitia_isochrone_pair(
                '5.1;45.1', '2026-01-16', '08:00', '09:00'
            )

        assert result['aller_geom'] is not None
        assert result['retour_geom'] is None
        assert result['intersection_geom'] is None

    def test_get_navitia_isochrone_pair_both_empty(self):
        responses = [{'isochrones': []}, {'isochrones': []}]

        with mock.patch(
            'c2corg_api.views.navitia.get_navitia_isochrone', side_effect=responses
        ):
            result = get_navitia_isochrone_pair(
                '5.1;45.1', '2026-01-16', '08:00', '09:00'
            )

        assert result == {
            'aller_geom': None,
            'retour_geom': None,
            'intersection_geom': None,
        }

    def test_get_navitia_isochrone_pair_override_duration(self):
        responses = [{'isochrones': []}, {'isochrones': []}]

        with mock.patch(
            'c2corg_api.views.navitia.get_navitia_isochrone', side_effect=responses
        ) as mock_get_iso:
            get_navitia_isochrone_pair(
                '5.1;45.1', '2026-01-16', '08:00', '09:00', override_duration_minutes=30
            )

        aller_call_params = mock_get_iso.call_args_list[0][0][0]
        assert aller_call_params['boundary_duration[]'] == 30 * 60

    # is_wp_round_trip_reachable
    def _make_access_wp_json(self):
        return {
            'geometry': {'geom': json.dumps({'type': 'Point', 'coordinates': [0, 0]})}
        }

    def _navitia_by_leg(self, aller_response, retour_response):
        """A navitia_get answering each leg, whatever the order they are asked"""

        def navitia_get(url, params=None, **kwargs):
            if params['datetime_represents'] == 'departure':
                return aller_response
            return retour_response

        return navitia_get

    def test_is_wp_round_trip_reachable_aller_only(self):
        wp_json = self._make_access_wp_json()

        aller_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T080000',
                    'arrival_date_time': '20260116T090000',
                }
            ]
        }
        retour_response = {'journeys': []}

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            mock_navitia_get.side_effect = self._navitia_by_leg(
                aller_response, retour_response
            )

            result = is_wp_round_trip_reachable(
                wp_json, '5.7;45.1', '2026-01-16', '08:00', '18:00', 3600
            )

        assert result['aller']['found'] is True
        assert result['aller']['departure'] == '20260116T080000'
        assert result['aller']['arrival'] == '20260116T090000'
        assert result['retour']['found'] is False
        assert result['retour']['departure'] is None
        assert result['compatible'] is False

    def test_is_wp_round_trip_reachable_retour_only(self):
        wp_json = self._make_access_wp_json()

        aller_response = {'journeys': []}
        retour_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T133000',
                    'arrival_date_time': '20260116T180000',
                }
            ]
        }

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            mock_navitia_get.side_effect = self._navitia_by_leg(
                aller_response, retour_response
            )

            result = is_wp_round_trip_reachable(
                wp_json, '5.7;45.1', '2026-01-16', '08:00', '18:00', 3600
            )

        assert result['aller']['found'] is False
        assert result['retour']['found'] is True
        assert result['retour']['departure'] == '20260116T133000'
        assert result['compatible'] is False

    def test_is_wp_round_trip_reachable_both_compatible(self):
        wp_json = self._make_access_wp_json()

        # aller arrives at 09:00, retour leaves at 13:30 : 4h30 available
        aller_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T080000',
                    'arrival_date_time': '20260116T090000',
                }
            ]
        }
        retour_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T133000',
                    'arrival_date_time': '20260116T180000',
                }
            ]
        }

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            mock_navitia_get.side_effect = self._navitia_by_leg(
                aller_response, retour_response
            )

            # 1 hour hiking duration, well below the 4h30 available
            result = is_wp_round_trip_reachable(
                wp_json, '5.7;45.1', '2026-01-16', '08:00', '18:00', 3600
            )

        assert result['aller']['found'] is True
        assert result['retour']['found'] is True
        assert result['compatible'] is True

    def test_is_wp_round_trip_reachable_both_incompatible(self):
        wp_json = self._make_access_wp_json()

        # aller arrives at 09:00, retour leaves at 09:30 : only 30 min
        aller_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T080000',
                    'arrival_date_time': '20260116T090000',
                }
            ]
        }
        retour_response = {
            'journeys': [
                {
                    'departure_date_time': '20260116T093000',
                    'arrival_date_time': '20260116T180000',
                }
            ]
        }

        with (
            mock.patch('c2corg_api.views.navitia.get_coverage') as mock_get_coverage,
            mock.patch('c2corg_api.views.navitia.navitia_get') as mock_navitia_get,
        ):
            mock_get_coverage.return_value = 'fr-se'
            mock_navitia_get.side_effect = self._navitia_by_leg(
                aller_response, retour_response
            )

            # 1 hour hiking duration : not enough time (only 30 min)
            result = is_wp_round_trip_reachable(
                wp_json, '5.7;45.1', '2026-01-16', '08:00', '18:00', 3600
            )

        assert result['aller']['found'] is True
        assert result['retour']['found'] is True
        assert result['compatible'] is False

    # _resolve_hiking_duration_seconds
    def test_resolve_hiking_duration_seconds_explicit(self):
        assert _resolve_hiking_duration_seconds('30', 1, 'route') == 1800
        assert _resolve_hiking_duration_seconds('30', 1, 'waypoint') == 1800

    def test_resolve_hiking_duration_seconds_waypoint_default(self):
        assert _resolve_hiking_duration_seconds(None, 1, 'waypoint') == 0

    def test_resolve_hiking_duration_seconds_route_default(self):
        fake_route = mock.Mock(calculated_duration=0.5)
        with mock.patch('c2corg_api.views.navitia.DBSession') as mock_db_session:
            query = mock_db_session.query.return_value
            query.filter.return_value.first.return_value = fake_route
            result = _resolve_hiking_duration_seconds(None, 42, 'route')

        assert result == 0.5 * 86400

    def test_resolve_hiking_duration_seconds_route_no_duration(self):
        fake_route = mock.Mock(calculated_duration=None)
        with mock.patch('c2corg_api.views.navitia.DBSession') as mock_db_session:
            query = mock_db_session.query.return_value
            query.filter.return_value.first.return_value = fake_route
            result = _resolve_hiking_duration_seconds(None, 42, 'route')

        assert result == 0

    # transport search: parameters, cache and /navitia/transportisochrones
    TRANSPORT_QUERY = (
        'from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00'
    )

    ISOCHRONES = {
        'aller_geom': {'type': 'Polygon', 'coordinates': [[[0, 0]]]},
        'retour_geom': {'type': 'Polygon', 'coordinates': [[[1, 1]]]},
        'intersection_geom': {'type': 'Polygon', 'coordinates': [[[2, 2]]]},
    }

    def _transport_params(self, **overrides):
        params = {
            'from': '5.1;45.1',
            'date': '2026-01-16',
            'min_departure': '08:00',
            'max_return': '18:00',
        }
        params.update(overrides)
        return params

    def test_parse_transport_params(self):
        transport = parse_transport_params(
            self._transport_params(**{'from': '5.12345;45.67891'})
        )

        # the starting point is rounded to about 110 m
        assert transport['from'] == '5.123;45.679'
        assert transport['date'] == '2026-01-16'
        assert transport['min_departure'] == '08:00'
        assert transport['max_return'] == '18:00'
        assert transport['max_duration'] is None
        assert transport['hiking_duration'] is None

    def test_parse_transport_params_prefix_and_optional_values(self):
        params = {
            'transport_' + name: value
            for name, value in self._transport_params(
                max_duration='90', hiking_duration='60'
            ).items()
        }

        transport = parse_transport_params(params, prefix='transport_')

        assert transport['from'] == '5.100;45.100'
        assert transport['max_duration'] == 90
        assert transport['hiking_duration'] == 60

    def test_parse_transport_params_invalid(self):
        invalid_params = [
            {'date': None},
            {'from': '5.1'},
            {'from': 'a;b'},
            {'from': '500;45'},
            {'date': '16/01/2026'},
            {'min_departure': '8h'},
            {'max_return': '25:00'},
            {'min_departure': '18:00', 'max_return': '08:00'},
            {'max_duration': 'abc'},
            {'hiking_duration': '-5'},
        ]
        for overrides in invalid_params:
            params = {
                key: value
                for key, value in self._transport_params(**overrides).items()
                if value is not None
            }
            with self.assertRaises(ValueError, msg=str(overrides)):
                parse_transport_params(params)

    def test_navitia_transportisochrones_invalid_params(self):
        for query in [
            'date=2026-01-16&min_departure=08:00&max_return=18:00',
            'from=5.1%3B45.1&date=2026-01-16&min_departure=18:00&max_return=08:00',
            'from=abc&date=2026-01-16&min_departure=08:00&max_return=18:00',
        ]:
            self.app.get('/navitia/transportisochrones?' + query, status=400)

    def test_navitia_transportisochrones(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
        ):
            mock_cache.return_value = FakeCache()
            mock_iso_pair.return_value = self.ISOCHRONES

            response = self.app.get(
                '/navitia/transportisochrones?from=5.12345%3B45.67891'
                '&date=2026-01-16&min_departure=08:00&max_return=18:00',
                status=200,
            )

            assert response.json == self.ISOCHRONES
            mock_iso_pair.assert_called_once_with(
                '5.123;45.679',
                '2026-01-16',
                '08:00',
                '18:00',
                override_duration_minutes=None,
            )

    def test_isochrones_are_computed_once_per_search(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
        ):
            mock_cache.return_value = FakeCache()
            mock_iso_pair.return_value = self.ISOCHRONES

            # the same search, and one starting about 30 m away: same entry
            for from_coords in ('5.1001;45.1001', '5.1001;45.1001', '5.1003;45.1002'):
                transport = parse_transport_params(
                    self._transport_params(**{'from': from_coords})
                )
                assert get_cached_isochrone_pair(transport) == self.ISOCHRONES
            assert mock_iso_pair.call_count == 1

            # another time, or another maximum duration: other isochrones
            for overrides in ({'max_return': '19:00'}, {'max_duration': '45'}):
                get_cached_isochrone_pair(
                    parse_transport_params(self._transport_params(**overrides))
                )
            assert mock_iso_pair.call_count == 3

    def test_incomplete_isochrones_are_not_cached(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
        ):
            mock_cache.return_value = FakeCache()
            mock_iso_pair.return_value = {
                'aller_geom': self.ISOCHRONES['aller_geom'],
                'retour_geom': None,
                'intersection_geom': None,
            }

            transport = parse_transport_params(self._transport_params())
            get_cached_isochrone_pair(transport)
            get_cached_isochrone_pair(transport)

            assert mock_iso_pair.call_count == 2

    def test_cache_failure_does_not_break_the_search(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
        ):
            mock_cache.side_effect = redis.ConnectionError('no redis')
            mock_iso_pair.return_value = self.ISOCHRONES

            transport = parse_transport_params(self._transport_params())

            assert get_cached_isochrone_pair(transport) == self.ISOCHRONES

    def test_transport_document_ids_route(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
            mock.patch(
                'c2corg_api.views.navitia.get_route_ids_within_geometry'
            ) as mock_get_route_ids,
            mock.patch(
                'c2corg_api.views.navitia._reproject_geojson_to_3857'
            ) as mock_reproject,
        ):
            mock_cache.return_value = FakeCache()
            mock_iso_pair.return_value = self.ISOCHRONES
            mock_reproject.return_value = 'POLYGON((0 0,1 1,2 2,0 0))'
            mock_get_route_ids.return_value = {3, 1, 2}

            transport = parse_transport_params(self._transport_params())

            assert get_cached_transport_document_ids(transport, 'route') == [1, 2, 3]
            mock_get_route_ids.assert_called_once_with(
                'POLYGON((0 0,1 1,2 2,0 0))', None
            )

            # the same search again (other filters changed): nothing is computed
            assert get_cached_transport_document_ids(transport, 'route') == [1, 2, 3]
            assert mock_get_route_ids.call_count == 1
            assert mock_iso_pair.call_count == 1

    def test_transport_document_ids_route_with_hiking_duration(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
            mock.patch(
                'c2corg_api.views.navitia.get_route_ids_within_geometry'
            ) as mock_get_route_ids,
            mock.patch(
                'c2corg_api.views.navitia._reproject_geojson_to_3857'
            ) as mock_reproject,
        ):
            mock_cache.return_value = FakeCache()
            mock_iso_pair.return_value = self.ISOCHRONES
            mock_reproject.return_value = 'POLYGON((0 0,1 1,2 2,0 0))'
            mock_get_route_ids.return_value = {1}

            transport = parse_transport_params(
                self._transport_params(hiking_duration='60')
            )
            get_cached_transport_document_ids(transport, 'route')

            # window = 08:00 -> 18:00 = 600 minutes = 36000 seconds
            mock_get_route_ids.assert_called_once_with(
                'POLYGON((0 0,1 1,2 2,0 0))', 36000
            )

    def test_transport_document_ids_waypoint_no_intersection(self):
        with (
            mock.patch('c2corg_api.views.navitia._cache_client') as mock_cache,
            mock.patch(
                'c2corg_api.views.navitia.get_navitia_isochrone_pair'
            ) as mock_iso_pair,
            mock.patch(
                'c2corg_api.views.navitia.get_waypoint_ids_within_geometry'
            ) as mock_get_wp_ids,
            mock.patch(
                'c2corg_api.views.navitia._reproject_geojson_to_3857'
            ) as mock_reproject,
        ):
            fake_cache = FakeCache()
            mock_cache.return_value = fake_cache
            mock_iso_pair.return_value = {
                'aller_geom': None,
                'retour_geom': None,
                'intersection_geom': None,
            }
            mock_get_wp_ids.return_value = set()

            transport = parse_transport_params(self._transport_params())

            assert get_cached_transport_document_ids(transport, 'waypoint') == []
            mock_reproject.assert_not_called()
            mock_get_wp_ids.assert_called_once_with(None)
            # nothing is kept: the isochrones may have failed temporarily
            assert fake_cache.data == {}

    # /navitia/roundtripreachable endpoint
    def test_navitia_roundtripreachable_missing_params(self):
        self.app.get(
            '/navitia/roundtripreachable?document_type=waypoint&from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00',
            status=400,
        )

    def test_navitia_roundtripreachable_invalid_document_type(self):
        self.app.get(
            '/navitia/roundtripreachable?document_id=1&document_type=invalid&from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00',
            status=400,
        )

    def test_navitia_roundtripreachable(self):
        with (
            mock.patch(
                'c2corg_api.views.navitia.prepare_round_trip_document'
            ) as mock_prepare,
            mock.patch(
                'c2corg_api.views.navitia.best_round_trip_result'
            ) as mock_best_result,
        ):
            mock_prepare.return_value = {'prepared': True}
            mock_best_result.return_value = {
                'aller': {
                    'found': True,
                    'departure': '20260116T080000',
                    'arrival': '20260116T090000',
                },
                'retour': {
                    'found': True,
                    'departure': '20260116T133000',
                    'arrival': '20260116T180000',
                },
                'compatible': True,
            }

            response = self.app.get(
                '/navitia/roundtripreachable?document_id=1&document_type=waypoint&from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00&hiking_duration=60',
                status=200,
            )

            data = json.loads(response.body.decode())

            assert data['compatible'] is True
            mock_prepare.assert_called_once_with(1, 'waypoint', '5.1;45.1', '60')
            mock_best_result.assert_called_once_with(
                {'prepared': True}, '5.1;45.1', '2026-01-16', '08:00', '18:00'
            )

    def test_navitia_roundtripreachable_no_access_waypoint(self):
        with mock.patch(
            'c2corg_api.views.navitia._get_access_waypoints_for_document'
        ) as mock_get_wps:
            mock_get_wps.return_value = []

            response = self.app.get(
                '/navitia/roundtripreachable?document_id=1&document_type=waypoint&from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00',
                status=200,
            )

            data = json.loads(response.body.decode())
            assert data['compatible'] is False
            assert data['aller']['found'] is False
            assert data['retour']['found'] is False

    # best_round_trip_result: access waypoints, traverses, early exit
    def _journeys_by_leg(self, timetable, calls):
        """A _query_navitia_journeys answering from `timetable`, which maps
        (waypoint coordinates, 'departure' for the aller / 'arrival' for the
        retour) to a journey, and recording the requests in `calls`"""

        def query(params, coverage):
            leg = params['datetime_represents']
            coords = params['to'] if leg == 'departure' else params['from']
            calls.append((leg, coords))
            journey = timetable.get((coords, leg))
            return {'journeys': [journey]} if journey else None

        return query

    def _aller_journey(self, arrival):
        return {
            'departure_date_time': '20260116T080000',
            'arrival_date_time': arrival,
        }

    def _retour_journey(self, departure):
        return {
            'departure_date_time': departure,
            'arrival_date_time': '20260116T180000',
        }

    def _target(self, document_id, lon, lat):
        return {
            'document_id': document_id,
            'lon': lon,
            'lat': lat,
            'coords': f'{lon};{lat}',
            'coverage': 'fr-se',
        }

    def _best_result(self, timetable, targets, hiking_duration_seconds, one_way):
        calls = []
        prepared = {
            'targets': targets,
            'hiking_duration_seconds': hiking_duration_seconds,
            'one_way': one_way,
        }
        with mock.patch(
            'c2corg_api.views.navitia._query_navitia_journeys',
            side_effect=self._journeys_by_leg(timetable, calls),
        ):
            result = best_round_trip_result(
                prepared, '5.7;45.1', '2026-01-16', '08:00', '18:00'
            )
        return result, calls

    def test_best_round_trip_result_traverse(self):
        # arrive by one end of the traverse, leave from the other one
        start = self._target(1, 6.0, 45.0)
        end = self._target(2, 6.5, 45.5)
        timetable = {
            (start['coords'], 'departure'): self._aller_journey('20260116T090000'),
            (end['coords'], 'arrival'): self._retour_journey('20260116T160000'),
        }

        result, _ = self._best_result(timetable, [start, end], 4 * 3600, True)

        assert result['compatible'] is True
        assert result['aller_waypoint_id'] == 1
        assert result['retour_waypoint_id'] == 2

    def test_best_round_trip_result_same_data_out_and_back(self):
        # an out-and-back route has to come back from where it arrived
        start = self._target(1, 6.0, 45.0)
        end = self._target(2, 6.5, 45.5)
        timetable = {
            (start['coords'], 'departure'): self._aller_journey('20260116T090000'),
            (end['coords'], 'arrival'): self._retour_journey('20260116T160000'),
        }

        result, _ = self._best_result(timetable, [start, end], 4 * 3600, False)

        assert result['compatible'] is False

    def test_best_round_trip_result_traverse_too_long(self):
        start = self._target(1, 6.0, 45.0)
        end = self._target(2, 6.5, 45.5)
        timetable = {
            (start['coords'], 'departure'): self._aller_journey('20260116T090000'),
            (end['coords'], 'arrival'): self._retour_journey('20260116T160000'),
        }

        # 7 hours between the aller and the retour, 8 needed
        result, _ = self._best_result(timetable, [start, end], 8 * 3600, True)

        assert result['compatible'] is False
        # the best legs found are still returned
        assert result['aller_waypoint_id'] == 1
        assert result['retour_waypoint_id'] == 2

    def test_best_round_trip_result_stops_at_first_working_waypoint(self):
        close = self._target(1, 6.0, 45.0)
        far = self._target(2, 9.0, 47.0)
        timetable = {
            (close['coords'], 'departure'): self._aller_journey('20260116T090000'),
            (close['coords'], 'arrival'): self._retour_journey('20260116T170000'),
            (far['coords'], 'departure'): self._aller_journey('20260116T100000'),
            (far['coords'], 'arrival'): self._retour_journey('20260116T171000'),
        }

        result, calls = self._best_result(timetable, [close, far], 3600, False)

        assert result['compatible'] is True
        assert result['aller_waypoint_id'] == 1
        assert result['retour_waypoint_id'] == 1
        # only the aller and retour of the first access waypoint were asked
        assert len(calls) == 2

    def test_best_round_trip_result_traverse_stops_at_first_working_pair(self):
        start = self._target(1, 6.0, 45.0)
        end = self._target(2, 6.5, 45.5)
        timetable = {
            (start['coords'], 'departure'): self._aller_journey('20260116T090000'),
            (start['coords'], 'arrival'): self._retour_journey('20260116T170000'),
            (end['coords'], 'departure'): self._aller_journey('20260116T100000'),
            (end['coords'], 'arrival'): self._retour_journey('20260116T171000'),
        }

        result, calls = self._best_result(timetable, [start, end], 3600, True)

        assert result['compatible'] is True
        assert len(calls) == 2

    def test_best_round_trip_result_without_access_waypoint(self):
        result, calls = self._best_result({}, [], 0, False)

        assert result['compatible'] is False
        assert result['aller']['found'] is False
        assert result['retour']['found'] is False
        assert result['aller_waypoint_id'] is None
        assert result['retour_waypoint_id'] is None
        assert calls == []

    def test_sort_targets_by_distance(self):
        targets = [
            self._target(3, 9.0, 47.0),
            self._target(1, 5.8, 45.1),
            self._target(2, 6.5, 45.5),
        ]

        ordered = _sort_targets_by_distance(targets, '5.7;45.1')

        assert [target['document_id'] for target in ordered] == [1, 2, 3]

    def test_is_one_way_route(self):
        for route_types, expected in [
            (['traverse'], True),
            (['loop', 'raid'], True),
            (['return_same_way'], False),
            ([], False),
            (None, False),
        ]:
            route = mock.Mock(route_types=route_types)
            with mock.patch('c2corg_api.views.navitia.DBSession') as mock_db_session:
                mock_db_session.query.return_value.filter.return_value.first.return_value = route  # noqa
                assert _is_one_way_route(42) is expected, str(route_types)

        with mock.patch('c2corg_api.views.navitia.DBSession') as mock_db_session:
            mock_db_session.query.return_value.filter.return_value.first.return_value = None  # noqa
            assert _is_one_way_route(42) is False

    def test_compute_round_trip_checks_documents_at_once_and_counts_them(self):
        job_id = 'job-123'
        checked = []

        def best_result(prepared, *args):
            checked.append(prepared['document_id'])
            return {
                'aller': {'found': True, 'departure': 'a', 'arrival': 'b'},
                'retour': {'found': True, 'departure': 'c', 'arrival': 'd'},
                'compatible': prepared['document_id'] % 2 == 0,
            }

        with (
            mock.patch(
                'c2corg_api.views.navitia.prepare_round_trip_document'
            ) as mock_prepare,
            mock.patch(
                'c2corg_api.views.navitia.best_round_trip_result',
                side_effect=best_result,
            ),
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
            mock.patch('c2corg_api.views.navitia._store_job_progress') as mock_progress,
        ):
            mock_prepare.side_effect = lambda document_id, *args: {
                'document_id': document_id
            }

            request = mock.Mock()
            request.GET = {
                # a document given twice is checked once
                'ids': '1,2,3,4,4',
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_routes(job_id, request)

        mock_redis = mock_redis_client.return_value
        assert sorted(checked) == [1, 2, 3, 4]
        mock_redis.set.assert_any_call(f'job:{job_id}:total', 4)
        mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')
        # the progress counts the documents checked so far, found and not found
        assert mock_progress.call_count == 4
        assert mock_progress.call_args_list[-1] == call(mock_redis, job_id, 4, 2, 2)

    def test_compute_round_trip_stops_on_error(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.prepare_round_trip_document'
            ) as mock_prepare,
            mock.patch(
                'c2corg_api.views.navitia.best_round_trip_result',
                side_effect=HTTPInternalServerError('Navitia is down'),
            ),
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            mock_prepare.return_value = {}

            request = mock.Mock()
            request.GET = {
                'ids': '1,2,3',
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_routes(job_id, request)

        mock_redis = mock_redis_client.return_value
        mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')
        assert not any(
            call_args[0][0] == f'job:{job_id}:result'
            for call_args in mock_redis.set.call_args_list
        )

    # compute_round_trip_reachable_routes / waypoints
    def test_compute_round_trip_reachable_routes(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.prepare_round_trip_document'
            ) as mock_prepare,
            mock.patch(
                'c2corg_api.views.navitia.best_round_trip_result'
            ) as mock_is_reachable,
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            mock_prepare.side_effect = lambda document_id, *args: {
                'document_id': document_id
            }

            def is_reachable_side_effect(
                prepared, from_coords, date, min_departure, max_return
            ):
                return {
                    'aller': {'found': True, 'departure': 'a', 'arrival': 'b'},
                    'retour': {'found': True, 'departure': 'c', 'arrival': 'd'},
                    'compatible': True,
                }

            mock_is_reachable.side_effect = is_reachable_side_effect

            mock_redis = mock_redis_client.return_value

            request = mock.Mock()
            request.GET = {
                'ids': '1,2',
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_routes(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:total', 2)
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            result_json = next(
                call[0][1]
                for call in mock_redis.set.call_args_list
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)

            assert result_data['total'] == 2
            assert result_data['results']['1']['compatible'] is True
            assert result_data['results']['2']['compatible'] is True

    def test_compute_round_trip_reachable_routes_above_threshold(self):
        job_id = 'job-123'

        with mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client:
            mock_redis = mock_redis_client.return_value

            request = mock.Mock()
            request.GET = {
                'ids': ','.join(str(i) for i in range(MAX_ROUTE_THRESHOLD + 1)),
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_routes(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')
            mock_redis.set.assert_any_call(
                f'job:{job_id}:error',
                "Couldn't proceed with computation : Too much routes found.",
            )
            assert not any(
                call[0][0] == f'job:{job_id}:result'
                for call in mock_redis.set.call_args_list
            )

    def test_compute_round_trip_reachable_waypoints(self):
        job_id = 'job-123'

        with (
            mock.patch(
                'c2corg_api.views.navitia.prepare_round_trip_document'
            ) as mock_prepare,
            mock.patch(
                'c2corg_api.views.navitia.best_round_trip_result'
            ) as mock_is_reachable,
            mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client,
        ):
            mock_prepare.side_effect = lambda document_id, *args: {
                'document_id': document_id
            }
            mock_is_reachable.return_value = {
                'aller': {'found': True, 'departure': 'a', 'arrival': 'b'},
                'retour': {'found': False, 'departure': None, 'arrival': None},
                'compatible': False,
            }

            mock_redis = mock_redis_client.return_value

            request = mock.Mock()
            request.GET = {
                'ids': '1',
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:total', 1)
            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'done')

            result_json = next(
                call[0][1]
                for call in mock_redis.set.call_args_list
                if call[0][0] == f'job:{job_id}:result'
            )
            result_data = json.loads(result_json)

            assert result_data['total'] == 1
            assert result_data['results']['1']['compatible'] is False

    def test_compute_round_trip_reachable_waypoints_above_threshold(self):
        job_id = 'job-123'

        with mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis_client:
            mock_redis = mock_redis_client.return_value

            request = mock.Mock()
            request.GET = {
                'ids': ','.join(str(i) for i in range(MAX_ROUTE_THRESHOLD + 1)),
                'from': '5.1;45.1',
                'date': '2026-01-16',
                'min_departure': '08:00',
                'max_return': '18:00',
            }

            compute_round_trip_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f'job:{job_id}:status', 'error')
            mock_redis.set.assert_any_call(
                f'job:{job_id}:error',
                "Couldn't proceed with computation : Too much waypoints found.",
            )

    def test_navitia_journeyroundtrip_start_missing_params(self, subtests):
        base_urls = [
            '/navitia/journeyroundtriproutes',
            '/navitia/journeyroundtripwaypoints',
        ]

        for base_url in base_urls:
            with subtests.test(base_url=base_url):
                # missing ids
                self.app.get(
                    base_url
                    + '/start?from=5.1%3B45.1&date=2026-01-16&min_departure=08:00&max_return=18:00',  # noqa
                    status=400,
                )

    def test_navitia_journeyroundtrip_start(self, subtests):
        test_cases = [
            ('/navitia/journeyroundtriproutes', compute_round_trip_reachable_routes),
            (
                '/navitia/journeyroundtripwaypoints',
                compute_round_trip_reachable_waypoints,
            ),
        ]

        for base_url, func in test_cases:
            with subtests.test(base_url=base_url, func=func):
                with mock.patch(
                    'c2corg_api.views.navitia.start_job_background'
                ) as mock_start:
                    mock_start.return_value = 'job-123'

                    response = self.app.get(
                        (
                            base_url + '/start?'
                            'ids=1,2&'
                            'from=5.1%3B45.1&'
                            'date=2026-01-16&'
                            'min_departure=08:00&'
                            'max_return=18:00'
                        ),
                        status=200,
                    )
                    assert json.loads(response.body.decode()) == 'job-123'
                    mock_start.assert_called_once_with(func, mock.ANY)

    def test_navitia_journeyroundtrip_result(self, subtests):
        urls = [
            '/navitia/journeyroundtriproutes/result/job-123',
            '/navitia/journeyroundtripwaypoints/result/job-123',
        ]

        for url in urls:
            with subtests.test(url=url):

                def fake_read_result(redis, job_id):
                    assert job_id == 'job-123'
                    return {'status': 'error', 'message': 'missing_result'}

                with (
                    mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis,
                    mock.patch(
                        'c2corg_api.views.navitia.read_result_from_redis',
                        side_effect=fake_read_result,
                    ) as mock_read_result,
                ):
                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(url, status=200)

                    body = response.body
                    assert json.loads(body.decode()) == {
                        'status': 'error',
                        'message': 'missing_result',
                    }
                    mock_read_result.assert_called_once_with(
                        mock_redis.return_value, 'job-123'
                    )

    def test_navitia_journeyroundtrip_progress(self, subtests):
        urls = [
            '/navitia/journeyroundtriproutes/progress/job-123',
            '/navitia/journeyroundtripwaypoints/progress/job-123',
        ]

        for url in urls:
            with subtests.test(url=url):
                fake_events = [b'data: {}\n\n']

                def fake_progress_stream(redis, job_id):
                    assert job_id == 'job-123'
                    for event in fake_events:
                        yield event

                with (
                    mock.patch('c2corg_api.views.navitia.redis_client') as mock_redis,
                    mock.patch(
                        'c2corg_api.views.navitia.progress_stream',
                        side_effect=fake_progress_stream,
                    ),
                ):
                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(url, status=200)

                    assert response.content_type == 'text/event-stream'
                    assert response.body == b''.join(fake_events)


class TestReachableIdsByGeometry(BaseTestCase):
    """
    Tests for get_route_ids_within_geometry (route.py) and
    get_waypoint_ids_within_geometry (waypoint.py) : these are kept here,
    alongside the other Itinevert/transport-accessibility tests, rather
    than in test_route.py/test_waypoint.py, since they exercise a single
    focused PostGIS query each and don't fit those files' REST-oriented
    (BaseDocumentTestRest) fixtures.
    """

    def setUp(self):
        BaseTestCase.setUp(self)
        self._add_test_data()

    def _add_test_data(self):
        from c2corg_api.views.route import get_route_ids_within_geometry
        from c2corg_api.views.waypoint import get_waypoint_ids_within_geometry

        self.get_route_ids_within_geometry = get_route_ids_within_geometry
        self.get_waypoint_ids_within_geometry = get_waypoint_ids_within_geometry

        # an access waypoint located at (0, 0) in EPSG:3857
        self.access_wp = Waypoint(
            waypoint_type='access',
            locales=[WaypointLocale(lang='en', title='Access wp')],
        )
        self.access_wp.geometry = DocumentGeometry(geom='SRID=3857;POINT(0 0)')
        self.session.add(self.access_wp)
        self.session.flush()

        # a waypoint far away, at (100000, 100000)
        self.far_wp = Waypoint(
            waypoint_type='access', locales=[WaypointLocale(lang='en', title='Far wp')]
        )
        self.far_wp.geometry = DocumentGeometry(geom='SRID=3857;POINT(100000 100000)')
        self.session.add(self.far_wp)
        self.session.flush()

        self.route = Route(
            activities=['hiking'],
            durations='1',
            calculated_duration=0.5,
            locales=[RouteLocale(lang='en', title='A hike')],
        )
        self.session.add(self.route)
        self.session.flush()

        self.session.add(
            Association.create(
                parent_document=self.route, child_document=self.access_wp
            )
        )
        self.session.flush()

        # a route with no access waypoint intersecting the geometry
        self.far_route = Route(
            activities=['hiking'],
            durations='1',
            calculated_duration=2.0,
            locales=[RouteLocale(lang='en', title='A far hike')],
        )
        self.session.add(self.far_route)
        self.session.flush()

        self.session.add(
            Association.create(
                parent_document=self.far_route, child_document=self.far_wp
            )
        )
        self.session.flush()

        # a small square around (0, 0), not covering the far waypoint
        self.geom_wkt = 'POLYGON((-10 -10, -10 10, 10 10, 10 -10, -10 -10))'

    def test_get_route_ids_within_geometry(self):
        ids = self.get_route_ids_within_geometry(self.geom_wkt)
        assert self.route.document_id in ids
        assert self.far_route.document_id not in ids

    def test_get_route_ids_within_geometry_no_geom(self):
        assert self.get_route_ids_within_geometry(None) == set()
        assert self.get_route_ids_within_geometry('') == set()

    def test_get_route_ids_within_geometry_duration_filter(self):
        # the route's calculated_duration is 0.5 days = 43200 seconds
        ids = self.get_route_ids_within_geometry(
            self.geom_wkt, max_duration_seconds=43200
        )
        assert self.route.document_id in ids

        ids = self.get_route_ids_within_geometry(
            self.geom_wkt, max_duration_seconds=3600
        )
        assert self.route.document_id not in ids

    def test_get_waypoint_ids_within_geometry(self):
        ids = self.get_waypoint_ids_within_geometry(self.geom_wkt)
        assert self.access_wp.document_id in ids
        assert self.far_wp.document_id not in ids

    def test_get_waypoint_ids_within_geometry_no_geom(self):
        assert self.get_waypoint_ids_within_geometry(None) == set()


class TestCoveragesCache(BaseTestCase):
    def setUp(self):
        super().setUp()
        clear_coverages_cache()

    def tearDown(self):
        clear_coverages_cache()
        super().tearDown()

    def test_coverage_polygons_are_loaded_once(self):
        coverage = mock.Mock(coverage_type='fr-se')
        coverage.geometry.geom_detail = 'wkb'

        with (
            mock.patch('c2corg_api.views.coverage.DBSession') as mock_db_session,
            mock.patch('c2corg_api.views.coverage.wkb_to_shape') as mock_to_shape,
        ):
            mock_db_session.query.return_value.all.return_value = [coverage]
            mock_to_shape.return_value = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

            assert get_coverage(5, 5) == 'fr-se'
            assert get_coverage(50, 50) is None
            assert get_coverages(Polygon([(1, 1), (2, 1), (2, 2)])) == ['fr-se']

            assert mock_db_session.query.call_count == 1
            assert mock_to_shape.call_count == 1
