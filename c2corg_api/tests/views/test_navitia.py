from unittest import mock
from shapely.geometry import Polygon
import json
import requests
from pyramid.httpexceptions import HTTPBadRequest
from unittest.mock import call
from c2corg_api.tests import BaseTestCase
from c2corg_api.views import to_json_dict
from c2corg_api.models.route import schema_route
import os
from datetime import datetime, time
from c2corg_api.views.navitia import start_job_background, \
    _store_job_progress, \
    get_job_status, \
    redis_client, \
    read_result_from_redis, \
    progress_stream, \
    compute_journey_reachable_routes, \
    compute_journey_reachable_waypoints, \
    navitia_get, \
    handle_navitia_response, \
    extract_meta_params, \
    extract_journey_params, \
    extract_isochrone_params, \
    is_wp_in_isochrone, \
    get_navitia_isochrone, \
    is_wp_journey_reachable, \
    MAX_TRIP_DURATION, \
    MIN_TRIP_DURATION, \
    BASE_URL

from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry
from pyramid.httpexceptions import HTTPInternalServerError

from c2corg_api.views.navitia import MAX_ROUTE_THRESHOLD


from dotenv import load_dotenv

# load .env into os.environ (call once)
load_dotenv()

NAVITIA_GET_PATH = "c2corg_api.views.navitia.navitia_get"
NAVITIA_REDIS_CLIENT_PATH = "c2corg_api.views.navitia.redis_client"
NAVITIA_KEY = os.getenv("NAVITIA_API_KEY", "test-key")


class TestNavitiaRestParams(BaseTestCase):
    # /navitia/journeys endpoint
    def test_journey_missing_required_params(self):
        with mock.patch.dict(os.environ, {"NAVITIA_API_KEY": NAVITIA_KEY}):
            # missing to
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&datetime=20260116T115100&datetime_represents=departure",  # noqa
                status=400
            )
            # missing from
            self.app.get(
                "/navitia/journeys?to=5.0;45.0&datetime=20260116T115100&datetime_represents=departure",  # noqa
                status=400
            )
            # missing datetime
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime_represents=departure",  # noqa
                status=400
            )
            # missing datetime_represents
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100",  # noqa
                status=400
            )

    def test_journey_invalid_coordinate_format(self):
        with mock.patch.dict(os.environ, {"NAVITIA_API_KEY": NAVITIA_KEY}):
            # invalid 'from'
            self.app.get(
                "/navitia/journeys?from=invalid&to=5.1;45.1&datetime=20260116T115100&datetime_represents=departure",  # noqa
                status=500)
            # invalid 'to'
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=notcoords&datetime=20260116T115100&datetime_represents=departure",  # noqa
                status=500)

    def test_journey_invalid_datetime(self):
        with mock.patch.dict(os.environ, {"NAVITIA_API_KEY": NAVITIA_KEY}):
            # invalid datetime
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=invalid&datetime_represents=departure",  # noqa
                status=500
            )
            # invalid datetime_represents
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100&datetime_represents=invalid",  # noqa
                status=500)

    def test_journey_missing_api_key(self):
        # ensure NAVITIA_API_KEY not set in env
        with mock.patch.dict(os.environ, {}, clear=True):
            self.app.get(
                "/navitia/journeys?from=5.0;45.0&to=5.1;45.1&datetime=20260116T115100&datetime_represents=departure",  # noqa
                status=500
            )

    def test_navitia_journey_success(self):
        # datetime parameter is today's date 08:00
        # so that we don't face the datetime out of production error
        dt = datetime.combine(
            datetime.today().date(),
            time(hour=8, minute=0, second=0)
        )
        dt_str = dt.strftime("%Y%m%dT%H%M%S")

        with mock.patch.dict(os.environ, {"NAVITIA_API_KEY": NAVITIA_KEY}):
            self.app.get(
                f"/navitia/journeys?"
                f"from=5.7357819%3B45.1875602&"
                f"to=5.166955054538887%3B45.07757475794273&"
                f"datetime={dt_str}&"
                f"datetime_represents=departure&"
                f"walking_speed=1.12&"
                f"max_walking_duration_to_pt=4464&"
                f"min_nb_journeys=3&"
                f"max_nb_transfers=-1",
                status=200,
            )

    # individual job handling functions
    def test_get_redis_client(self):
        assert redis_client() is not None

    def test_start_job(self):
        with mock.patch(NAVITIA_REDIS_CLIENT_PATH) as mock_redis_client:
            mock_r = mock_redis_client.return_value

            result = start_job_background(lambda *_: None, request={"a": 1})

            job_id = result["job_id"]

            mock_r.set.assert_any_call(f"job:{job_id}:progress", 0)
            mock_r.set.assert_any_call(f"job:{job_id}:status", "running")

    def test_store_job_progress(self):
        with mock.patch(NAVITIA_REDIS_CLIENT_PATH) as mock_redis_client:
            mock_r = mock_redis_client.return_value
            job_id = "job-123"

            _store_job_progress(mock_r, job_id, count=5, found=3, not_found=2)

            mock_r.set.assert_any_call(f"job:{job_id}:progress", 5)
            mock_r.set.assert_any_call(f"job:{job_id}:found", 3)
            mock_r.set.assert_any_call(f"job:{job_id}:not_found", 2)

            mock_r.publish.assert_any_call(
                f"job:{job_id}:events", "progress:5")
            mock_r.publish.assert_any_call(f"job:{job_id}:events", "found:3")
            mock_r.publish.assert_any_call(
                f"job:{job_id}:events", "not_found:2")

    def test_get_job_status(self):
        r = mock.Mock()
        job_id = "job-123"

        r.get.return_value = "running".encode("utf-8")

        status, payload = get_job_status(r, job_id)

        r.get.assert_called_once_with(f"job:{job_id}:status")
        assert status == "running"
        assert payload == "running"

    def test_get_job_status_unknown_job(self):
        r = mock.Mock()
        job_id = "job-123"

        r.get.return_value = None

        status, payload = get_job_status(r, job_id)

        r.get.assert_called_once_with(f"job:{job_id}:status")
        assert status is None
        assert payload == {"error": "unknown_job_id"}

    def test_read_result_from_redis_unknown_status(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f"job:{job_id}:status":
                return "abcd".encode("utf-8")

        r = mock.Mock()
        job_id = "job-123"

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f"job:{job_id}:status")
        assert response == {"error": "unknown_status", "status": "abcd"}

    def test_read_result_from_redis_job_error(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f"job:{job_id}:status":
                return "error".encode("utf-8")
            if args[0] == f"job:{job_id}:error":
                return "fake error message".encode("utf-8")

        r = mock.Mock()
        job_id = "job-123"

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls([
            call(f"job:{job_id}:status"),
            call(f"job:{job_id}:error")
        ])
        assert response == {
            "status": "error",
            "message": "fake error message"
        }

    def test_read_result_from_redis_unknown_job(self):
        r = mock.Mock()
        job_id = "job-123"

        r.get.return_value = None

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f"job:{job_id}:status")
        assert response == {"error": "unknown_job_id"}

    def test_read_result_from_redis_job_running(self):
        r = mock.Mock()
        job_id = "job-123"

        r.get.return_value = "running".encode("utf-8")

        response = read_result_from_redis(r, job_id)

        r.get.assert_called_once_with(f"job:{job_id}:status")
        assert response == {"status": "running"}

    def test_read_result_from_redis_job_done_no_data(self):
        def error_side_effect(*args, **kwargs):
            if args[0] == f"job:{job_id}:status":
                return "done".encode("utf-8")
            if args[0] == f"job:{job_id}:result":
                return None

        r = mock.Mock()
        job_id = "job-123"

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls([
            call(f"job:{job_id}:status"),
            call(f"job:{job_id}:result")
        ])
        assert response == {
            "status": "error",
            "message": "missing_result"
        }

    def test_read_result_from_redis_job_done_success(self):
        def error_side_effect(*args, **kwargs):
            r1 = to_json_dict(
                Route(activities=['hiking', 'rock_climbing']),
                schema_route
            )
            r2 = to_json_dict(
                Route(activities=['slacklining', 'rock_climbing']),
                schema_route
            )
            routes = [r1, r2]
            if args[0] == f"job:{job_id}:status":
                return "done".encode("utf-8")
            if args[0] == f"job:{job_id}:result":
                return json.dumps({'documents': routes, 'total': len(routes)})

        r1 = to_json_dict(
            Route(activities=['hiking', 'rock_climbing']),
            schema_route
        )
        r2 = to_json_dict(
            Route(activities=['slacklining', 'rock_climbing']),
            schema_route
        )
        routes = [r1, r2]

        r = mock.Mock()
        job_id = "job-123"

        r.get.side_effect = error_side_effect

        response = read_result_from_redis(r, job_id)

        r.get.assert_has_calls([
            call(f"job:{job_id}:status"),
            call(f"job:{job_id}:result")
        ])
        assert response == {
            "status": "done",
            "result": {'documents': routes, 'total': len(routes)}
        }

    def test_progress_stream_done(self):
        r = mock.Mock()

        # Simulate Redis responses in call order
        r.get.side_effect = [
            b"10",          # progress
            b"7",           # found
            b"3",           # not_found
            b"10",          # total
            b"done",        # status → terminates loop
        ]

        with mock.patch("c2corg_api.views.navitia.time.sleep"):
            gen = progress_stream(r, job_id="job-123")

            first = next(gen)
            second = next(gen)

        payload = json.loads(first.decode().replace("data: ", "").strip())

        assert payload == {
            "progress": 10,
            "total": 10,
            "found": 7,
            "not_found": 3,
        }

        assert second == b"event: done\ndata: done\n\n"

    def test_progress_stream_init(self):
        r = mock.Mock()
        r.get.side_effect = [
            None, None, None, None,  # progress fields
            b"running",
        ]

        with mock.patch("c2corg_api.views.navitia.time.sleep"):
            gen = progress_stream(r, job_id="123")
            output = next(gen)

        payload = json.loads(output.decode().replace("data: ", "").strip())

        assert payload == {
            "progress": 0,
            "total": 0,
            "found": 0,
            "not_found": 0,
        }

    def test_progress_stream_error(self):
        r = mock.Mock()
        r.get.side_effect = [
            b"5",          # progress
            b"3",           # found
            b"2",           # not_found
            b"10",          # total
            b"error",       # status → terminates loop
            b"{'msg': 'error message'}"
        ]

        with mock.patch("c2corg_api.views.navitia.time.sleep"):
            gen = progress_stream(r, job_id="123")
            next(gen)
            second = next(gen)

        assert second.startswith(b"event: error")
        assert b'"msg": "error message"' in second

    # /navitia/journeyreachableroutes endpoints (includes job handling)
    # /navitia/journeyreachableroutes/start endpoint
    # /navitia/journeyreachablewaypoints/start endpoint
    def test_navitia_journeyreachabledocs_start(self):
        test_cases = [
            ("/navitia/journeyreachableroutes",
             compute_journey_reachable_routes),
            ("/navitia/journeyreachablewaypoints",
             compute_journey_reachable_waypoints),
        ]

        for base_url, func in test_cases:
            with self.subTest(base_url=base_url, func=func):
                with mock.patch("c2corg_api.views.navitia.start_job_background") as mock_start:  # noqa
                    mock_start.return_value = "job-123"

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
                        status=200
                    )
                    assert json.loads(response.body.decode()) == "job-123"
                    mock_start.assert_called_once_with(
                        func,
                        mock.ANY
                    )

    def test_navitia_journeyreachabledocs_start_missing_params(self):
        base_urls = [
            "/navitia/journeyreachableroutes",
            "/navitia/journeyreachablewaypoints",
        ]

        for base_url in base_urls:
            with self.subTest(base_url=base_url):
                # missing datetime
                self.app.get(
                    base_url + '/start?&datetime_represents=departure&from=5.677893899999996%3B45.1929973&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400
                )

                # missing datetime represents
                self.app.get(
                    base_url + '/start?datetime=20260122T143500&from=5.677893899999996%3B45.1929973&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400
                )

                # missing from
                self.app.get(
                    base_url + '/start?datetime=20260122T143500&datetime_represents=departure&walking_speed=1.12&max_walking_duration_to_pt=4464',  # noqa
                    status=400
                )

                # missing walking speed
                self.app.get(
                    base_url + '/start?datetime=20260122T143500&datetime_represents=departure&from=5.677893899999996%3B45.1929973&max_walking_duration_to_pt=4464',  # noqa
                    status=400
                )

                # missing max_walking_duration_to_pt
                self.app.get(
                    base_url + '/start?datetime=20260122T143500&datetime_represents=departure&from=5.677893899999996%3B45.1929973&walking_speed=1.12',  # noqa
                    status=400
                )

    # /navitia/journeyreachableroutes/progress endpoint
    # /navitia/journeyreachablewaypoints/progress endpoint
    def test_navitia_journeyreachabledocs_progress(self):
        urls = [
            "/navitia/journeyreachableroutes/progress/job-123",
            "/navitia/journeyreachablewaypoints/progress/job-123",
        ]

        for url in urls:
            with self.subTest(url=url):
                fake_events = [
                    b"data: %s\n\n" % json.dumps({
                        "progress": 0,
                        "total": 10,
                        "found": 0,
                        "not_found": 0
                    }).encode("utf-8"),

                    b"data: %s\n\n" % json.dumps({
                        "progress": 5,
                        "total": 10,
                        "found": 4,
                        "not_found": 1
                    }).encode("utf-8"),

                    b"data: %s\n\n" % json.dumps({
                        "progress": 9,
                        "total": 10,
                        "found": 6,
                        "not_found": 3
                    }).encode("utf-8"),
                ]

                def fake_progress_stream(redis, job_id):
                    assert job_id == "job-123"
                    for event in fake_events:
                        yield event

                with mock.patch(
                    "c2corg_api.views.navitia.redis_client"
                ) as mock_redis, mock.patch(
                    "c2corg_api.views.navitia.progress_stream",
                    side_effect=fake_progress_stream,
                ) as mock_progress:

                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(
                        url,
                        status=200
                    )

                    # Content type should be SSE
                    assert response.content_type == "text/event-stream"
                    body = response.body
                    assert body == b"".join(fake_events)

                    mock_progress.assert_called_once_with(
                        mock_redis.return_value, "job-123")

    # /navitia/journeyreachableroutes/result endpoint
    # /navitia/journeyreachablewaypoints/result endpoint
    def test_navitia_journeyreachabledocs_result(self):
        urls = [
            "/navitia/journeyreachableroutes/result/job-123",
            "/navitia/journeyreachablewaypoints/result/job-123",
        ]

        for url in urls:
            with self.subTest(url=url):
                def fake_read_result(redis, job_id):
                    assert job_id == "job-123"
                    return {
                        "status": "error",
                        "message": "missing_result"
                    }

                with mock.patch(
                    "c2corg_api.views.navitia.redis_client"
                ) as mock_redis, mock.patch(
                    "c2corg_api.views.navitia.read_result_from_redis",
                    side_effect=fake_read_result,
                ) as mock_read_result:
                    mock_redis.return_value = mock.Mock()

                    response = self.app.get(
                        url,
                        status=200
                    )

                    body = response.body
                    assert json.loads(body.decode()) == {
                        "status": "error",
                        "message": "missing_result"
                    }

                    mock_read_result.assert_called_once_with(
                        mock_redis.return_value,
                        "job-123"
                    )

    # /navitia/isochronereachableroutes endpoint
    def test_navitia_isochronereachableroutes(self):
        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_isochrone_params") as mock_extract_isochrone_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_route_query_with_waypoints") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_waypoints_from_results") as mock_collect_wp,  # noqa
            mock.patch("c2corg_api.views.navitia.get_navitia_isochrone") as mock_get_iso,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_in_isochrone") as mock_is_in_iso,  # noqa
            mock.patch("c2corg_api.views.navitia.to_json_dict") as mock_to_json  # noqa
        ):

            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}

            mock_extract_isochrone_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'boundary_duration[]': 3600  # 1 hour
            }

            mock_query = mock.Mock()
            r1 = Route(document_id='1', activities=['hiking'])
            r2 = Route(document_id='2', activities=['slacklining'])
            results = [
                (r1, [{'document_id': '1'}], [{'document_id': '1'}]),
                (r2, [{'document_id': '1'}], [{'document_id': '2'}])
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
                )
            }
            mock_collect_wp.return_value = [
                Waypoint(document_id='1', waypoint_type='access'),
                Waypoint(document_id='2', waypoint_type='access')
            ]

            # any polygon
            mock_get_iso.return_value = {
                "isochrones": [{"geojson": {
                    "type": "Polygon",
                    "coordinates": [[
                        [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]
                    ]]
                }}]
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
                "/navitia/isochronesreachableroutes?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600",  # noqa
                status=200
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'
            assert result_data['isochron_geom'] == {
                "type": "Polygon",
                "coordinates": [[
                    [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]
                ]]
            }

    def test_navitia_isochronereachableroutes_no_result(self):
        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_isochrone_params") as mock_extract_isochrone_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_route_query_with_waypoints") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_waypoints_from_results") as mock_collect_wp,  # noqa
            mock.patch("c2corg_api.views.navitia.get_navitia_isochrone") as mock_get_iso,  # noqa
        ):

            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}

            mock_extract_isochrone_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'boundary_duration[]': 3600  # 1 hour
            }

            mock_query = mock.Mock()
            r1 = Route(document_id='1', activities=['hiking'])
            r2 = Route(document_id='2', activities=['slacklining'])
            results = [
                (r1, [{'document_id': '1'}], [{'document_id': '1'}]),
                (r2, [{'document_id': '1'}], [{'document_id': '2'}])
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
                )
            }
            mock_collect_wp.return_value = [
                Waypoint(document_id='1', waypoint_type='access'),
                Waypoint(document_id='2', waypoint_type='access')
            ]

            # any polygon
            mock_get_iso.return_value = {
                "isochrones": []
            }

            result = self.app.get(
                "/navitia/isochronesreachableroutes?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600",  # noqa
                status=200
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 0
            assert result_data['isochron_geom'] == ''

    # /navitia/isochronereachablewaypoints endpoint
    def test_navitia_isochronereachablewaypoints(self):
        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_isochrone_params") as mock_extract_isochrone_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_waypoints_query") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.get_navitia_isochrone") as mock_get_iso,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_in_isochrone") as mock_is_in_iso,  # noqa
            mock.patch("c2corg_api.views.navitia.to_json_dict") as mock_to_json  # noqa
        ):

            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}

            mock_extract_isochrone_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'boundary_duration[]': 3600  # 1 hour
            }

            mock_query = mock.Mock()
            results = [
                (Waypoint(document_id='1', waypoint_type='access'),
                 [{'document_id': '1'}]),
                (Waypoint(document_id='2', waypoint_type='access'),
                 [{'document_id': '1'}])
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
                )
            }

            # any polygon
            mock_get_iso.return_value = {
                "isochrones": [{"geojson": {
                    "type": "Polygon",
                    "coordinates": [[
                        [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]
                    ]]
                }}]
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
                "/navitia/isochronesreachablewaypoints?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600",  # noqa
                status=200
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'
            assert result_data['isochron_geom'] == {
                "type": "Polygon",
                "coordinates": [[
                    [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]
                ]]
            }

    def test_navitia_isochronereachablewaypoints_no_result(self):
        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_isochrone_params") as mock_extract_isochrone_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_waypoints_query") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.get_navitia_isochrone") as mock_get_iso,  # noqa
        ):

            # mock meta/isochrone params
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}

            mock_extract_isochrone_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'boundary_duration[]': 3600  # 1 hour
            }

            mock_query = mock.Mock()
            results = [
                (Waypoint(document_id='1', waypoint_type='access'),
                 [{'document_id': '1'}]),
                (Waypoint(document_id='2', waypoint_type='access'),
                 [{'document_id': '2'}])
            ]
            mock_query.all.return_value = results
            mock_build_query.return_value = (mock_query, len(results))

            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
                )
            }

            # any polygon
            mock_get_iso.return_value = {
                "isochrones": []
            }

            result = self.app.get(
                "/navitia/isochronesreachablewaypoints?from=5.7357819%3B45.1875602&datetime=20260116T115100&datetime_represents=departure&boundary_duration=3600",  # noqa
                status=200
            )

            # parse JSON body
            result_data = json.loads(result.body.decode('utf-8'))

            assert result_data['total'] == 0
            assert result_data['isochron_geom'] == ''

    # individual business functions used in routes
    def test_compute_journey_reachable_routes(self):
        job_id = "job-123"

        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_route_query_with_waypoints") as mock_build_reachable_route_query_with_waypoints,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_waypoints_from_results") as mock_collect_wp,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_journey_params") as mock_extract_journey_params,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_journey_reachable") as mock_is_reachable,  # noqa
            mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client,  # noqa
        ):

            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}
            mock_extract_journey_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'walking_speed': "1.12",
                'max_walking_duration_to_pt': "4464",
                'to': "5.166955054538887%3B45.07757475794273"
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = [
                (Route(activities=['hiking', 'rock_climbing']), [
                 {"document_id": "1"}], [{"document_id": "1"}]),
                (Route(activities=['hiking']), [
                 {"document_id": "1"}], [{"document_id": "2"}]),
            ]
            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query, len(mock_query.all.return_value))

            # --- mock areas / waypoints ---
            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(
                        geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
                    )
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
            mock_redis.set.assert_any_call(f"job:{job_id}:total", 2)

            # Check Redis was called with correct job status
            mock_redis.set.assert_any_call(f"job:{job_id}:status", "done")

            # Get the stored result from Redis
            result_json = mock_redis.set.call_args_list
            result_json = next(
                call[0][1] for call in result_json
                if call[0][0] == f"job:{job_id}:result"
            )
            result_data = json.loads(result_json)
            routes = result_data["documents"]

            assert len(routes) == 1
            assert routes[0]["activities"] == ["hiking", "rock_climbing"]

    def test_compute_journey_reachable_routes_no_results(self):
        job_id = "job-123"

        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_route_query_with_waypoints") as mock_build_reachable_route_query_with_waypoints,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_waypoints_from_results") as mock_collect_wp,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_journey_params") as mock_extract_journey_params,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_journey_reachable") as mock_is_reachable,  # noqa
            mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client,  # noqa
        ):

            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}
            mock_extract_journey_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'walking_speed': "1.12",
                'max_walking_duration_to_pt': "4464",
                'to': "5.166955054538887%3B45.07757475794273"
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = []

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query, len(mock_query.all.return_value)
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
            mock_redis.set.assert_any_call(f"job:{job_id}:total", 0)

            # Check Redis was called with correct job status
            mock_redis.set.assert_any_call(f"job:{job_id}:status", "done")

            # Get the stored result from Redis
            result_json = mock_redis.set.call_args_list
            result_json = next(
                call[0][1] for call in result_json
                if call[0][0] == f"job:{job_id}:result"
            )
            result_data = json.loads(result_json)
            routes = result_data["documents"]

            assert len(routes) == 0

    def test_compute_journey_reachable_routes_above_threshold(self):
        job_id = "job-123"

        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_route_query_with_waypoints") as mock_build_reachable_route_query_with_waypoints,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_waypoints_from_results") as mock_collect_wp,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_journey_params") as mock_extract_journey_params,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_journey_reachable") as mock_is_reachable,  # noqa
            mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client,  # noqa
        ):

            # --- setup meta/journey params ---
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}
            mock_extract_journey_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'walking_speed': "1.12",
                'max_walking_duration_to_pt': "4464",
                'to': "5.166955054538887%3B45.07757475794273"
            }

            # --- mock query ---
            mock_query = mock.Mock()
            mock_query.all.return_value = [
                (Route(), [], []) for _ in range(MAX_ROUTE_THRESHOLD + 1)
            ]

            # --- mock Redis ---
            mock_redis = mock_redis_client.return_value

            mock_build_reachable_route_query_with_waypoints.return_value = (
                mock_query, len(mock_query.all.return_value)
            )

            request = mock.Mock()
            request.GET = {}

            compute_journey_reachable_routes(job_id, request)

            mock_redis.set.assert_any_call(
                f"job:{job_id}:status", "error"
            )

            mock_redis.set.assert_any_call(
                f"job:{job_id}:error",
                "Couldn't proceed with computation : Too much routes found."
            )

            # Ensure no result was written
            self.assertFalse(any(
                call[0][0] == f"job:{job_id}:result"
                for call in mock_redis.set.call_args_list
            ))

    def test_compute_journey_reachable_waypoints(self):
        job_id = "job-123"

        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_journey_params") as mock_extract_journey_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_waypoints_query") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_journey_reachable") as mock_is_reachable,  # noqa
            mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client,  # noqa
        ):
            # mock meta/journey params
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}
            mock_extract_journey_params.return_value = {
                'from': "5.7357819%3B45.1875602",
                'datetime': "20260116T115100",
                'datetime_represents': "departure",
                'walking_speed': "1.12",
                'max_walking_duration_to_pt': "4464",
                'to': "5.166955054538887%3B45.07757475794273"
            }

            # mock query results
            mock_query = mock.Mock()
            # list of tuples: (waypoint, areas)
            mock_query.all.return_value = [
                (Waypoint(document_id='1', waypoint_type='access'),
                 [{"document_id": "1"}]),
                (Waypoint(document_id='2', waypoint_type='access'),
                 [{"document_id": "1"}])
            ]
            mock_build_query.return_value = (
                mock_query, len(mock_query.all.return_value))

            # mock areas
            mock_collect_areas.return_value = {
                '1': Area(
                    document_id='1',
                    area_type='range',
                    geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))')  # noqa
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
            mock_redis.set.assert_any_call(f"job:{job_id}:total", 2)

            # check final status
            mock_redis.set.assert_any_call(f"job:{job_id}:status", "done")

            # result contains only reachable waypoint
            result_json = next(
                call[0][1] for call in mock_redis.set.call_args_list
                if call[0][0] == f"job:{job_id}:result"
            )
            result_data = json.loads(result_json)
            assert result_data['total'] == 1
            assert result_data['documents'][0]['document_id'] == '1'

    def test_compute_journey_reachable_waypoints_no_results(self):
        job_id = "job-123"

        with (
            mock.patch("c2corg_api.views.navitia.extract_meta_params") as mock_extract_meta_params,  # noqa
            mock.patch("c2corg_api.views.navitia.extract_journey_params") as mock_extract_journey_params,  # noqa
            mock.patch("c2corg_api.views.navitia.build_reachable_waypoints_query") as mock_build_query,  # noqa
            mock.patch("c2corg_api.views.navitia.collect_areas_from_results") as mock_collect_areas,  # noqa
            mock.patch("c2corg_api.views.navitia.is_wp_journey_reachable") as mock_is_reachable,  # noqa
            mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client,  # noqa
        ):
            mock_extract_meta_params.return_value = {
                'offset': 0, 'limit': 100, 'lang': 'fr'}
            mock_extract_journey_params.return_value = {
                'from': '...', 'to': '...'}

            mock_query = mock.Mock()
            mock_query.all.return_value = []
            mock_build_query.return_value = (mock_query, 0)

            mock_collect_areas.return_value = {}

            mock_redis = mock_redis_client.return_value

            request = mock.Mock()

            # only one area
            request.GET = {'a': '1'}
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f"job:{job_id}:total", 0)
            mock_redis.set.assert_any_call(f"job:{job_id}:status", "done")

            # result empty
            result_json = next(
                call[0][1] for call in mock_redis.set.call_args_list
                if call[0][0] == f"job:{job_id}:result"
            )
            result_data = json.loads(result_json)
            assert result_data['total'] == 0
            assert result_data['documents'] == []

    def test_compute_journey_reachable_waypoints_missing_area(self):
        job_id = "job-123"

        with mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client:  # noqa
            mock_redis = mock_redis_client.return_value
            request = mock.Mock()
            # no areas
            request.GET = {}
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f"job:{job_id}:status", "error")
            mock_redis.set.assert_any_call(
                f"job:{job_id}:error", 'Missing filter : area is required')

    def test_compute_journey_reachable_waypoints_multiple_areas(self):
        job_id = "job-123"

        with mock.patch("c2corg_api.views.navitia.redis_client") as mock_redis_client:  # noqa
            mock_redis = mock_redis_client.return_value
            request = mock.Mock()
            request.GET = {'a': '1,2'}  # multiple areas
            compute_journey_reachable_waypoints(job_id, request)

            mock_redis.set.assert_any_call(f"job:{job_id}:status", "error")
            mock_redis.set.assert_any_call(
                f"job:{job_id}:error", 'Only one filtering area is allowed')

    def test_handle_navitia_response_success(self):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "some_data"}

        result = handle_navitia_response(mock_response)
        self.assertEqual(result, {"data": "some_data"})

    def test_handle_navitia_response_401(self):
        mock_response = mock.Mock()
        mock_response.status_code = 401

        with self.assertRaises(HTTPInternalServerError):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_400(self):
        mock_response = mock.Mock()
        mock_response.status_code = 400

        with self.assertRaises(HTTPBadRequest):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_404_no_journey(self):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": {"id": "no_origin"}}

        result = handle_navitia_response(mock_response)
        self.assertIsNone(result)

    def test_handle_navitia_response_404_other_error(self):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": {"id": "some_other_error"}}

        with self.assertRaises(HTTPInternalServerError):
            handle_navitia_response(mock_response)

    def test_handle_navitia_response_other_error(self):
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.ok = False

        with self.assertRaises(HTTPInternalServerError):
            handle_navitia_response(mock_response)

    def test_navitia_get_normal_operation(self):
        with mock.patch("requests.get") as mock_get:
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.ok = True
            mock_response.json.return_value = {"data": "some_data"}
            mock_get.return_value = mock_response

            result = navitia_get(BASE_URL)
            self.assertEqual(result, {"data": "some_data"})

    def test_navitia_get_timeout(self):
        with mock.patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout

            with self.assertRaises(HTTPInternalServerError):
                navitia_get(BASE_URL)

    def test_navitia_get_other_request_exception(self):
        with mock.patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException(
                "An error occurred")

            with self.assertRaises(HTTPInternalServerError):
                navitia_get(BASE_URL)

    def test_navitia_extract_meta_params_no_lang(self):
        mock_request = mock.Mock()
        mock_request.validated = {}
        result = extract_meta_params(mock_request)
        assert result == {
            'offset': 0,
            'limit': 2000,
            'lang': None,
        }

    def test_navitia_extract_meta_params_with_lang(self):
        mock_request = mock.Mock()
        mock_request.validated = {
            'limit': 50,
            'lang': 'fr',
        }
        result = extract_meta_params(mock_request)
        assert result == {
            'offset': 0,
            'limit': 2000,
            'lang': 'fr',
        }

    def test_navitia_extract_journey_params(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464'
        }
        result = extract_journey_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'datetime_represents': 'departure',
            'walking_speed': '1.12',
            'max_walking_duration_to_pt': '4464',
            'to': ''
        }

    def test_navitia_extract_isochrone_params_upper_bounded(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(MAX_TRIP_DURATION * 60 + 10000),
            'datetime_represents': 'departure'
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MAX_TRIP_DURATION * 60,
            'datetime_represents': 'departure'
        }

    def test_navitia_extract_isochrone_params_lower_bounded(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(MIN_TRIP_DURATION * 60 - 10000),
            'datetime_represents': 'departure'
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MIN_TRIP_DURATION * 60,
            'datetime_represents': 'departure'
        }

    def test_navitia_extract_isochrone_params(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': str(int((MAX_TRIP_DURATION * 60 + MIN_TRIP_DURATION * 60) / 2)),  # noqa
            'datetime_represents': 'departure'
        }
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': int((MAX_TRIP_DURATION * 60 + MIN_TRIP_DURATION * 60) / 2),  # noqa
            'datetime_represents': 'departure'
        }

    def test_navitia_extract_isochrone_params_multiple_boundaries(self):
        mock_request = mock.Mock()
        mock_request.params = {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration': "4000, 8000, 12000",
            'datetime_represents': 'departure'
        }
        # default value is MAX_TRIP_DURATION
        result = extract_isochrone_params(mock_request)
        assert result == {
            'from': '5.1;45.1',
            'datetime': '20260116T115100',
            'boundary_duration[]': MAX_TRIP_DURATION * 60,
            'datetime_represents': 'departure'
        }

    def test_is_wp_in_isochrone(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            "geom": json.dumps({
                "type": "Point",
                "coordinates": [665870.779788, 5653070.161742]
            })
        }

        # Create a mock isochrone geometry
        isochrone_geom = Polygon(
            [(1.0, 40.0), (1.0, 50.0), (10.0, 50.0), (10.0, 40.0)]
        )

        result = is_wp_in_isochrone(mock_wp, isochrone_geom)

        self.assertTrue(result)

    def test_is_wp_not_in_isochrone(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            "geom": json.dumps({
                "type": "Point",
                "coordinates": [0, 0]
            })
        }

        # Create a mock isochrone geometry
        isochrone_geom = Polygon(
            [(4.0, 24.0), (4.0, 26.0), (6.0, 26.0), (6.0, 24.0)]
        )

        result = is_wp_in_isochrone(mock_wp, isochrone_geom)

        self.assertFalse(result)

    def test_get_navitia_isochrone(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = "5;45"
        with (
            mock.patch("c2corg_api.views.navitia.get_coverage") as mock_get_coverage,  # noqa
            mock.patch("c2corg_api.views.navitia.navitia_get") as mock_navitia_get  # noqa
        ):
            mock_get_coverage.return_value = 'fr-se'
            get_navitia_isochrone(mock_isochrone_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + "/coverage/fr-se/isochrones",
                params=mock_isochrone_params,
                headers={"Authorization": NAVITIA_KEY}
            )

    def test_get_navitia_isochrone_missing_api_key(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = "5;45"
        with (
            mock.patch.dict(os.environ, {}, clear=True)
        ):
            with self.assertRaises(HTTPInternalServerError):
                get_navitia_isochrone(mock_isochrone_params)

    def test_get_navitia_isochrone_no_source_coverage(self):
        mock_isochrone_params = mock.Mock()
        # lon, lat
        mock_isochrone_params.get.return_value = "5;45"
        with (
            mock.patch("c2corg_api.views.navitia.get_coverage") as mock_get_coverage,  # noqa
        ):
            mock_get_coverage.return_value = None
            with self.assertRaises(HTTPInternalServerError):
                get_navitia_isochrone(mock_isochrone_params)

    def test_is_wp_journey_reachable(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            "geom": json.dumps({
                "type": "Point",
                "coordinates": [0, 0]
            })
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': "5.7357819%3B45.1875602",
            'datetime': "20260116T115100",
            'datetime_represents': "departure",
            'walking_speed': "1.12",
            'max_walking_duration_to_pt': "4464",
            'to': ''
        }

        with (
            mock.patch("c2corg_api.views.navitia.get_coverage") as mock_get_coverage,  # noqa
            mock.patch("c2corg_api.views.navitia.navitia_get") as mock_navitia_get  # noqa
        ):
            mock_get_coverage.return_value = 'fr-se'
            is_wp_journey_reachable(mock_wp, mock_journey_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + "/coverage/fr-se/journeys",
                params=mock_journey_params,
                headers={"Authorization": NAVITIA_KEY}
            )

    def test_is_wp_journey_reachable_missing_api_key(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            "geom": json.dumps({
                "type": "Point",
                "coordinates": [0, 0]
            })
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': "5.7357819%3B45.1875602",
            'datetime': "20260116T115100",
            'datetime_represents': "departure",
            'walking_speed': "1.12",
            'max_walking_duration_to_pt': "4464",
            'to': ''
        }

        with (
            mock.patch.dict(os.environ, {}, clear=True)
        ):
            with self.assertRaises(HTTPInternalServerError):
                is_wp_journey_reachable(mock_wp, mock_journey_params)

    def test_is_wp_journey_reachable_no_destination_coverage(self):
        mock_wp = mock.Mock()
        mock_wp.get.return_value = {
            "geom": json.dumps({
                "type": "Point",
                "coordinates": [0, 0]
            })
        }

        mock_journey_params = mock.Mock()
        mock_journey_params = {
            'from': "5.7357819%3B45.1875602",
            'datetime': "20260116T115100",
            'datetime_represents': "departure",
            'walking_speed': "1.12",
            'max_walking_duration_to_pt': "4464",
            'to': ''
        }

        with (
            mock.patch("c2corg_api.views.navitia.get_coverage") as mock_get_coverage,  # noqa
            mock.patch("c2corg_api.views.navitia.navitia_get") as mock_navitia_get  # noqa
        ):
            mock_get_coverage.return_value = None
            is_wp_journey_reachable(mock_wp, mock_journey_params)

            mock_navitia_get.assert_called_once_with(
                BASE_URL + "/journeys",
                params=mock_journey_params,
                headers={"Authorization": NAVITIA_KEY}
            )
