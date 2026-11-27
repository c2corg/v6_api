import hashlib
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as date_type
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anyio
import redis
import requests
from anyio import to_thread
from fastapi.responses import StreamingResponse
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform as shapely_transform
from sqlalchemy import or_

from c2corg_api.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPServiceUnavailable,
    HTTPTooManyRequests,
    HTTPUnauthorized,
)
from c2corg_api.models import DBSession
from c2corg_api.models.area import Area
from c2corg_api.models.association import Association
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.schemas.area import area_listing_schema
from c2corg_api.schemas.route import route_schema
from c2corg_api.schemas.waypoint import waypoint_schema
from c2corg_api.views import to_json_dict
from c2corg_api.views.coverage import get_coverage
from c2corg_api.views.route import (
    build_reachable_route_query_with_waypoints,
    classify_routes_within_geometry,
    route_duration_days,
)
from c2corg_api.views.waypoint import (
    build_reachable_waypoints_query,
    get_waypoint_ids_within_geometry,
)

log = logging.getLogger(__name__)

# When editing these constants, make sure to edit them in the front too
# (itinevert-service)
MAX_ROUTE_THRESHOLD = 50
MAX_TRIP_DURATION = 240
MIN_TRIP_DURATION = 20

# Routes done one way: the way back starts from another access waypoint
ONE_WAY_ROUTE_TYPES = ('traverse', 'raid', 'expedition')

# Number of documents whose round trip is checked at the same time by the
# batch jobs (each one makes its 2 Navitia requests at once)
ROUND_TRIP_DEFAULT_WORKERS = 3

# redis to store job's value (progress, result, error...): see
# configure_jobs_redis
_jobs_redis_pool = None
_cache_redis_pool = None
# the values of a job expire after its last write: long enough for the UI to
# read the result of a finished job
JOB_TTL = 3600  # seconds
# the jobs a process runs at once, and the delay before trying again
MAX_RUNNING_JOBS = 4
JOB_RETRY_AFTER = 10  # seconds
_running_jobs = threading.BoundedSemaphore(MAX_RUNNING_JOBS)
# the longest a progress stream follows a job
STREAM_MAX_DURATION = 600  # seconds

BASE_URL = 'https://api.navitia.io/v1'


def validate_navitia_params(request, **kwargs):
    """Validate the required parameters for the Navitia API."""
    required_params = ['from', 'to', 'datetime', 'datetime_represents']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')


def read_journeys(request):
    """
    Endpoint to retrieve trips from the Navitia API.

    Required query string parameters:
    - from: starting coordinates (format: longitude;latitude)
    - to: arrival coordinates (format: longitude;latitude)
    - datetime: date and hour (format ISO 8601)
    - datetime_represents: 'departure' or 'arrival'
    """
    # Retrieve navitia API Key from env var
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    # Build journey api parameters
    params = {
        'from': request.params.get('from'),
        'to': request.params.get('to'),
        'datetime': request.params.get('datetime'),
        'datetime_represents': request.params.get('datetime_represents'),
    }

    # Add optional params
    optional_params = [
        'max_duration_to_pt',
        'walking_speed',
        'bike_speed',
        'bss_speed',
        'car_speed',
        'forbidden_uris',
        'allowed_id',
        'first_section_mode',
        'last_section_mode',
        'max_walking_duration_to_pt',
        'max_nb_transfers',
        'min_nb_journeys',
        'max_bike_duration_to_pt',
        'max_bss_duration_to_pt',
        'max_car_duration_to_pt',
        'timeframe_duration',
        'max_walking_direct_path_duration',
        'wheelchair',
        'traveler_type',
        'data_freshness',
    ]

    for param in optional_params:
        if param in request.params:
            params[param] = request.params.get(param)

    return navitia_get(
        BASE_URL + '/journeys',
        params=params,
        headers={'Authorization': api_key},
    )


def validate_journey_reachable_params(request, **kwargs):
    """Validate the required parameters for the journey reachable doc route."""
    required_params = [
        'from',
        'datetime',
        'datetime_represents',
        'walking_speed',
        'max_walking_duration_to_pt',
    ]

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')


def start_journey_reachable_routes(request):
    """Start a job finding the journey-reachable routes, return its id."""
    return start_job_background(compute_journey_reachable_routes, request)


def start_journey_reachable_waypoints(request):
    """Start a job finding the journey-reachable waypoints, return its id."""
    return start_job_background(compute_journey_reachable_waypoints, request)


def read_journey_reachable_routes_result(request):
    """Get the result of a reachable-routes job.

    Get the result of the job : get journey reachable routes
    returns the result.
    """
    r = redis_client()
    job_id = request.matchdict.get('job_id')
    return read_result_from_redis(r, job_id)


def read_journey_reachable_waypoints_result(request):
    """Get the result of a reachable-waypoints job.

    Get the result of the job : get journey reachable waypoints
    returns the result.
    """
    r = redis_client()
    job_id = request.matchdict.get('job_id')
    return read_result_from_redis(r, job_id)


def read_journey_reachable_routes_progress(request):
    """Monitor progress of job id for journey reachable routes."""
    r = redis_client()
    job_id = request.matchdict.get('job_id')
    return _event_stream(progress_stream(r, job_id))


def read_journey_reachable_waypoints_progress(request):
    """Monitor progress of job id for journey reachable waypoints."""
    r = redis_client()
    job_id = request.matchdict.get('job_id')
    return _event_stream(progress_stream(r, job_id))


def validate_round_trip_batch_params(request, **kwargs):
    """Validate the parameters of the round-trip batch verification jobs.

    Validates the required parameters for the round-trip batch
    verification jobs (an explicit shortlist of document ids, plus the
    same temporal parameters used for a single-item check).
    """
    required_params = ['ids', 'from', 'date', 'min_departure', 'max_return']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')

    _validate_transport_window_param(request)


def start_round_trip_routes(request):
    """Start a job checking the round trip to a shortlist of routes, return its id."""
    return start_job_background(compute_round_trip_reachable_routes, request)


def start_round_trip_waypoints(request):
    """Start a job checking the round trip to some waypoints, return its id."""
    return start_job_background(compute_round_trip_reachable_waypoints, request)


def read_round_trip_routes_result(request):
    """Get the result of a round-trip routes job."""
    return read_result_from_redis(redis_client(), request.matchdict.get('job_id'))


def read_round_trip_waypoints_result(request):
    """Get the result of a round-trip waypoints job."""
    return read_result_from_redis(redis_client(), request.matchdict.get('job_id'))


def read_round_trip_routes_progress(request):
    """Monitor the progress of a round-trip routes job."""
    return _event_stream(
        progress_stream(redis_client(), request.matchdict.get('job_id'))
    )


def read_round_trip_waypoints_progress(request):
    """Monitor the progress of a round-trip waypoints job."""
    return _event_stream(
        progress_stream(redis_client(), request.matchdict.get('job_id'))
    )


def compute_journey_reachable_routes(job_id, request):
    """Get the routes reachable with a Navitia journey.

    Get all routes matching filters in params, that are reachable
    (means there exists a Navitia journey for at least one of
    their waypoints of type access).

    NOTE : the number of routes after applying filters,
    has to be < MAX_ROUTE_THRESHOLD,
    to reduce number of queries towards Navitia journey API

    the result can be found inside redis
    """
    r = redis_client()
    try:
        meta_params = extract_meta_params(request)
        journey_params = extract_journey_params(request)
        query, count = build_reachable_route_query_with_waypoints(
            request.GET, meta_params
        )
        if query is None:
            results = []
        else:
            results = query.all()

        if len(results) > MAX_ROUTE_THRESHOLD:
            raise HTTPBadRequest(
                "Couldn't proceed with computation : Too much routes found."
            )

        areas_map = collect_areas_from_results(results, 1)
        wp_objects = collect_waypoints_from_results(results)

        total = len(wp_objects)
        log.info('Number of NAVITIA journey queries : %d', total)
        _set_job_value(r, job_id, 'total', total)

        count = found = not_found = 0
        navitia_wp_map = {}

        for wp in wp_objects:
            result = is_wp_journey_reachable(
                to_json_dict(wp, waypoint_schema), journey_params
            )
            navitia_wp_map[wp.document_id] = result
            count += 1
            if result:
                found += 1
            else:
                not_found += 1
            _store_job_progress(r, job_id, count, found, not_found)

        routes = []
        for route, areas, waypoints in results:
            journey_exists = any(
                navitia_wp_map.get(wp.get('document_id')) for wp in waypoints
            )
            if not journey_exists:
                continue
            json_areas = []
            for area in areas or []:
                area_obj = areas_map.get(area.get('document_id'))
                if area_obj:
                    json_areas.append(to_json_dict(area_obj, area_listing_schema))
            route.areas = json_areas
            routes.append(to_json_dict(route, route_schema, True))

        _set_job_value(
            r,
            job_id,
            'result',
            json.dumps({'documents': routes, 'total': len(routes)}),
        )
        _set_job_value(r, job_id, 'status', 'done')
    except Exception as exc:
        log.exception(str(exc))
        _set_job_value(r, job_id, 'status', 'error')
        _set_job_value(r, job_id, 'error', json.dumps(_job_error(exc)))
    finally:
        _end_thread_db_session()


def compute_journey_reachable_waypoints(job_id, request):
    """Get the waypoints reachable with a Navitia journey.

    Get all waypoints matching filters in params, that are reachable
    (means there exists a Navitia journey for at least one of
    their waypoints of type access).

    NOTE : the waypoints have to be filtered by one area (and not more)
    to reduce number of request towards Navitia Journey API

    the result can be found inside redis
    """
    r = redis_client()
    try:
        meta_params = extract_meta_params(request)
        journey_params = extract_journey_params(request)

        # Ensure areas filter is provided and normalized
        areas_param = None
        try:
            areas_param = request.GET['a']
            if isinstance(areas_param, str):
                areas_list = areas_param.split(',')
            else:
                areas_list = list(areas_param)
        except Exception:
            areas_list = None

        if areas_list is None:
            raise HTTPBadRequest('Missing filter : area is required')
        if len(areas_list) > 1:
            raise HTTPBadRequest('Only one filtering area is allowed')

        query, count = build_reachable_waypoints_query(request.GET, meta_params)
        # no reachable waypoint: no query
        results = [] if query is None else query.all()

        areas_map = collect_areas_from_results(results, 1)

        total = len(results)
        log.info('Number of NAVITIA journey queries : %d', total)
        _set_job_value(r, job_id, 'total', total)

        count = found = not_found = 0
        waypoints = []

        for waypoint, areas in results:
            count += 1
            r.publish(f'job:{job_id}:events', f'not_found:{not_found}')
            reachable = is_wp_journey_reachable(
                to_json_dict(waypoint, waypoint_schema), journey_params
            )
            if reachable:
                found += 1
                json_areas = []
                for area in areas or []:
                    area_obj = areas_map.get(area.get('document_id'))
                    if area_obj:
                        json_areas.append(to_json_dict(area_obj, area_listing_schema))
                waypoint.areas = json_areas
                waypoints.append(to_json_dict(waypoint, waypoint_schema, True))
            else:
                not_found += 1
            _store_job_progress(r, job_id, count, found, not_found)

        _set_job_value(
            r,
            job_id,
            'result',
            json.dumps({'documents': waypoints, 'total': len(waypoints)}),
        )
        _set_job_value(r, job_id, 'status', 'done')
    except Exception as exc:
        log.exception('Error computing reachable waypoints')
        _set_job_value(r, job_id, 'status', 'error')
        _set_job_value(r, job_id, 'error', json.dumps(_job_error(exc)))
    finally:
        _end_thread_db_session()


def _compute_round_trip_reachable(
    job_id, request, document_type, too_many_error_message
):
    """Verify the round-trip reachability of a shortlist of documents.

    Shared implementation for compute_round_trip_reachable_routes and
    compute_round_trip_reachable_waypoints : verify round-trip (aller +
    retour) reachability, using real Navitia timetables, for an explicit
    shortlist of document ids (unlike the transport search filter of the
    topoguide, which only uses the isochrones).

    NOTE : MAX_ROUTE_THRESHOLD is enforced here, as this is a batch of
    up to 2 Navitia journey calls (aller + retour) per access waypoint
    of every requested document.

    The full structured per-item result (not a filtered list) is stored
    in redis under job:%s:result, as:
        {"results": {"<document_id>": {"aller": {...}, "retour": {...},
                                        "compatible": bool}, ...},
         "total": N}
    A route of an unknown duration is not checked (no Navitia request): its
    result is {"compatible": null, "duration_unknown": true}.

    The retour is looked for on `return_date` (the day of the aller by default).
    """
    r = redis_client()
    try:
        ids_param = request.GET.get('ids', '')
        ids = [int(doc_id) for doc_id in ids_param.split(',') if doc_id]
        ids = list(dict.fromkeys(ids))

        if len(ids) > MAX_ROUTE_THRESHOLD:
            raise HTTPBadRequest(too_many_error_message)

        from_coords = request.GET.get('from')
        date = request.GET.get('date')
        min_departure = request.GET.get('min_departure')
        max_return = request.GET.get('max_return')
        return_date = request.GET.get('return_date') or None
        hiking_duration_param = request.GET.get('hiking_duration')

        total = len(ids)
        log.info('Number of round-trip verifications : %d', total)
        r.set(f'job:{job_id}:total', total)

        # the database is read here: the threads below only call Navitia
        prepared_documents = {
            document_id: prepare_round_trip_document(
                document_id, document_type, from_coords, hiking_duration_param
            )
            for document_id in ids
        }

        count = found = not_found = 0
        results = {}

        # Several documents are checked at the same time, the time of the job
        # being the one of the Navitia requests. Their number stays small to
        # respect the Navitia rate limit.
        with ThreadPoolExecutor(max_workers=_round_trip_max_workers()) as executor:
            futures = {
                executor.submit(
                    best_round_trip_result,
                    prepared,
                    from_coords,
                    date,
                    min_departure,
                    max_return,
                    return_date,
                ): document_id
                for document_id, prepared in prepared_documents.items()
            }

            try:
                for future in as_completed(futures):
                    item_result = future.result()
                    results[str(futures[future])] = item_result

                    count += 1
                    if item_result['compatible']:
                        found += 1
                    else:
                        not_found += 1
                    _store_job_progress(r, job_id, count, found, not_found)
            except BaseException:
                # no need to go on with the other documents
                executor.shutdown(wait=True, cancel_futures=True)
                raise

        r.set(f'job:{job_id}:result', json.dumps({'results': results, 'total': total}))
        r.set(f'job:{job_id}:status', 'done')
    except Exception as exc:
        log.exception(str(exc))
        r.set(f'job:{job_id}:status', 'error')
        r.set(f'job:{job_id}:error', str(exc))
    finally:
        _end_thread_db_session()


def compute_round_trip_reachable_routes(job_id, request):
    """Verify the round-trip reachability of a shortlist of routes.

    Verify round-trip (aller + retour) reachability for an explicit
    shortlist of route ids (see _compute_round_trip_reachable).
    the result can be found inside redis.
    """
    _compute_round_trip_reachable(
        job_id,
        request,
        'route',
        "Couldn't proceed with computation : Too much routes found.",
    )


def compute_round_trip_reachable_waypoints(job_id, request):
    """Verify the round-trip reachability of a shortlist of waypoints.

    Verify round-trip (aller + retour) reachability for an explicit
    shortlist of waypoint ids (see _compute_round_trip_reachable).
    the result can be found inside redis.
    """
    _compute_round_trip_reachable(
        job_id,
        request,
        'waypoint',
        "Couldn't proceed with computation : Too much waypoints found.",
    )


def validate_isochrone_reachable_params(request, **kwargs):
    """Validate the required parameters for the isochrone reachable doc route."""
    required_params = ['from', 'datetime', 'datetime_represents', 'boundary_duration']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')


def read_isochrone_reachable_routes(request):
    """Get the routes with an access waypoint inside the isochron.

    Get all routes matching filters in params, that have at least
    one waypoint of type access that is inside the isochron.
    The isochron is created by querying navitia api
    with specific parameters, see validate_isochrone_reachable_params func.
    """
    meta_params = extract_meta_params(request)

    isochrone_params = extract_isochrone_params(request)

    query, _ = build_reachable_route_query_with_waypoints(request.GET, meta_params)

    if query is None:
        results = []
    else:
        results = query.all()

    areas_map = collect_areas_from_results(results, 1)

    response = get_navitia_isochrone(isochrone_params)

    routes = []
    geojson = ''
    # if isochrone found
    if len(response['isochrones']) > 0:
        geojson = response['isochrones'][0]['geojson']
        isochrone_geom = shape(geojson)

        wp_objects = collect_waypoints_from_results(results)

        navitia_wp_map = {
            wp.document_id: is_wp_in_isochrone(
                to_json_dict(wp, waypoint_schema), isochrone_geom
            )
            for wp in wp_objects
        }

        for route, areas, waypoints in results:
            # check if a journey exists for route
            # (at least one wp has a journey associated)
            one_wp_in_isochrone = False
            for wp in waypoints:
                wp_id = wp.get('document_id')
                one_wp_in_isochrone |= navitia_wp_map.get(wp_id)

            if one_wp_in_isochrone:
                json_areas = []

                if areas is None:
                    areas = []

                for area in areas:
                    area_obj = areas_map.get(area.get('document_id'))
                    if area_obj:
                        json_areas.append(to_json_dict(area_obj, area_listing_schema))

                # assign JSON areas to the waypoint
                route.areas = json_areas
                route_dict = to_json_dict(route, route_schema, True)
                routes.append(route_dict)

    return {'documents': routes, 'total': len(routes), 'isochron_geom': geojson}


def read_isochrone_reachable_waypoints(request):
    """Get the waypoints inside the isochron.

    Get all waypoints matching filters in params,
    that are inside the isochron.
    The isochron is created by querying navitia api
    with specific parameters, see validate_isochrone_reachable_params func.
    """
    meta_params = extract_meta_params(request)

    isochrone_params = extract_isochrone_params(request)

    query, _ = build_reachable_waypoints_query(request.GET, meta_params)

    # no reachable waypoint: no query
    results = [] if query is None else query.all()

    # manage areas for waypoints
    areas_map = collect_areas_from_results(results, 1)

    response = get_navitia_isochrone(isochrone_params)

    waypoints = []
    geojson = ''
    # if isochrone found
    if len(response['isochrones']) > 0:
        geojson = response['isochrones'][0]['geojson']
        isochrone_geom = shape(geojson)

        for waypoint, areas in results:
            # check if wp is in isochrone
            if is_wp_in_isochrone(
                to_json_dict(waypoint, waypoint_schema), isochrone_geom
            ):
                json_areas = []
                if areas is None:
                    areas = []

                for area in areas:
                    area_obj = areas_map.get(area.get('document_id'))
                    if area_obj:
                        json_areas.append(to_json_dict(area_obj, area_listing_schema))

                # assign JSON areas to the waypoint
                waypoint.areas = json_areas
                wp_dict = to_json_dict(waypoint, waypoint_schema, True)
                waypoints.append(wp_dict)

    return {
        'documents': waypoints,
        'total': len(waypoints),
        'isochron_geom': geojson,
    }


# --- Transport accessibility filter -------------------------------------
#
# The topoguide can be filtered on the documents reachable by public
# transport from a starting point, with `transport_*` query parameters (see
# parse_transport_params). The expensive parts, the 2 Navitia isochrones and
# the PostGIS query, are cached in redis, so that the same search (by the same
# user changing other filters, or by anybody else) is computed once.

# The starting point is rounded to this number of decimals (about 110 m):
# Navitia snaps it to the closest street/stop anyway, and a coarser point
# lets the searches starting from the same area share their cache.
TRANSPORT_COORDINATE_DECIMALS = 3

# Public transport timetables change rarely: keep the isochrones one day
TRANSPORT_ISOCHRONES_CACHE_TTL = 24 * 3600
# The matching documents change when a document is created or modified
TRANSPORT_DOCUMENT_IDS_CACHE_TTL = 3600

_TIME_PATTERN = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')

# The search space of a transport search is kept small: it bounds what one
# can make the API compute (each new search costs 2 Navitia isochrones) and
# makes the searches of different users share the cache. The UI rounds the
# times and bounds the dates the same way.
# the times of a search are on the quarter hour
TRANSPORT_TIME_STEP_MINUTES = 15
# the dates of a search are from today (the day before, for the time zones
# behind) to 6 months ahead, in the time zone of the timetables
TRANSPORT_MAX_MONTHS_AHEAD = 6
TRANSPORT_TIME_ZONE = ZoneInfo('Europe/Paris')


def transport_date_range(today=None):
    """Return the first and last dates a transport search may use."""
    if today is None:
        today = datetime.now(TRANSPORT_TIME_ZONE).date()
    month_index = today.month - 1 + TRANSPORT_MAX_MONTHS_AHEAD
    year, month = today.year + month_index // 12, month_index % 12 + 1
    # the same day 6 months later, or the last day of that month
    next_month = date_type(year + month // 12, month % 12 + 1, 1)
    last = min(
        date_type(year, month, 1) + timedelta(days=today.day - 1),
        next_month - timedelta(days=1),
    )
    return today - timedelta(days=1), last


def check_transport_window(date, min_departure, max_return, return_date=None):
    """Check the dates and times of a transport search.

    The dates are 'YYYY-MM-DD', within transport_date_range, the return
    not before the departure; the times are 'HH:MM', on the quarter hour, the
    return after the departure. Raises a ValueError describing the problem.
    """
    return_date = return_date or date
    _check_return_date(date, return_date)

    first, last = transport_date_range()
    for name, value in (('date', date), ('return_date', return_date)):
        day = datetime.strptime(value, '%Y-%m-%d').date()  # noqa: DTZ007
        if not first <= day <= last:
            raise ValueError(
                f"'{name}' must be between {first.isoformat()} and {last.isoformat()}"
            )

    for name, value in (('min_departure', min_departure), ('max_return', max_return)):
        if not value or not _TIME_PATTERN.match(value):
            raise ValueError(f"'{name}' must be formatted as 'HH:MM'")
        if int(value[3:5]) % TRANSPORT_TIME_STEP_MINUTES:
            raise ValueError(
                f"'{name}' must be on the quarter hour (:00, :15, :30, :45)"
            )

    if _window_minutes(date, min_departure, return_date, max_return) <= 0:
        raise ValueError("'max_return' must be after 'min_departure'")


def normalize_transport_from(from_coords):
    """Return the 'lon;lat' starting point, rounded.

    Returns the 'lon;lat' starting point rounded to
    TRANSPORT_COORDINATE_DECIMALS, or raises a ValueError if it is invalid.
    """
    try:
        lon_str, lat_str = from_coords.split(';')
        lon, lat = float(lon_str), float(lat_str)
    except (AttributeError, ValueError) as e:
        raise ValueError("'from' must be formatted as 'longitude;latitude'") from e

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("'from' is not a valid coordinate")

    decimals = TRANSPORT_COORDINATE_DECIMALS

    return f'{lon:.{decimals}f};{lat:.{decimals}f}'


def _parse_positive_int(name, value):
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except ValueError as e:
        raise ValueError(f"'{name}' must be an integer") from e
    if number < 0:
        raise ValueError(f"'{name}' must not be negative")
    return number


def parse_transport_params(params, prefix=''):
    """Validate and normalize the transport search parameters.

    Validate and normalize the transport search parameters found in `params`
    (the query string), where each name is preceded by `prefix`:
    from ('lon;lat'), date ('YYYY-MM-DD'), min_departure and max_return
    ('HH:MM'), the optional return_date ('YYYY-MM-DD', the date of `max_return`,
    the one of `date` by default) and the optional max_duration and
    hiking_duration (minutes).

    Returns a dict with those keys (the optional ones being None when not
    given), or raises a ValueError describing the problem.
    """
    missing = [
        prefix + name
        for name in ('from', 'date', 'min_departure', 'max_return')
        if not params.get(prefix + name)
    ]
    if missing:
        raise ValueError('Parameter {} required'.format(', '.join(missing)))

    date = params.get(prefix + 'date')
    times = {
        name: params.get(prefix + name) for name in ('min_departure', 'max_return')
    }
    return_date = params.get(prefix + 'return_date') or date
    check_transport_window(
        date, times['min_departure'], times['max_return'], return_date
    )

    return {
        'from': normalize_transport_from(params.get(prefix + 'from')),
        'date': date,
        'return_date': return_date,
        'min_departure': times['min_departure'],
        'max_return': times['max_return'],
        'max_duration': _parse_positive_int(
            'max_duration', params.get(prefix + 'max_duration')
        ),
        'hiking_duration': _parse_positive_int(
            'hiking_duration', params.get(prefix + 'hiking_duration')
        ),
    }


def _cache_client():
    """Redis client for the cache: a missing redis must not slow requests."""
    if _cache_redis_pool is None:
        raise RuntimeError('configure_jobs_redis was not called')
    return redis.Redis(connection_pool=_cache_redis_pool)


def _cache_key(kind, **parts):
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode('utf-8'))
    return f'transport:{kind}:{digest.hexdigest()}'


def _cache_get(key):
    """Return the cached value, or None if missing or if redis fails."""
    try:
        cached = _cache_client().get(key)
        return json.loads(cached) if cached else None
    except redis.RedisError, ValueError:
        log.warning('Could not read %s from the cache', key, exc_info=True)
        return None


def _cache_set(key, value, ttl):
    try:
        _cache_client().set(key, json.dumps(value), ex=ttl)
    except redis.RedisError:
        log.warning('Could not write %s to the cache', key, exc_info=True)


def get_cached_isochrone_pair(transport):
    """Return the isochrones of a transport search, computed once.

    The aller/retour/intersection isochrones of a transport search (see
    get_navitia_isochrone_pair), computed once per search.
    """
    boundary_duration = _resolve_boundary_duration_seconds(
        transport['min_departure'],
        transport['max_return'],
        transport['max_duration'],
        window_minutes=_transport_window_minutes(transport),
    )
    key = _cache_key(
        'isochrones',
        origin=transport['from'],
        date=transport['date'],
        return_date=transport['return_date'],
        min_departure=transport['min_departure'],
        max_return=transport['max_return'],
        boundary_duration=boundary_duration,
    )

    cached = _cache_get(key)
    if cached is not None:
        return cached

    isochrones = get_navitia_isochrone_pair(
        transport['from'],
        transport['date'],
        transport['min_departure'],
        transport['max_return'],
        override_duration_minutes=transport['max_duration'],
        return_date=transport['return_date'],
    )

    # an incomplete result can be a temporary failure: do not keep it
    if isochrones['aller_geom'] and isochrones['retour_geom']:
        _cache_set(key, isochrones, TRANSPORT_ISOCHRONES_CACHE_TTL)

    return isochrones


def get_cached_transport_document_ids(transport, document_type):
    """Return the documents within the isochrones of a transport search.

    The ids of the routes or waypoints (depending on `document_type`) having
    an access waypoint within the intersection of the aller and retour
    isochrones of a transport search, as
    `{'ids': [...], 'unverifiable_ids': [...]}` (both sorted): the routes of
    an unknown duration are in `unverifiable_ids` (they may be reachable, but
    cannot be checked), the other documents in `ids`.
    """
    max_duration_seconds = None
    if document_type == 'route' and transport['hiking_duration']:
        # A precise budget would be
        # (max_return - min_departure) - transit_time_estimate,
        # but transit time is only known per-candidate (it would
        # require a Navitia journey call per route). As a first
        # cut / acceptable approximation, use the full transport
        # window as the max allowed duration of the route.
        max_duration_seconds = _transport_window_minutes(transport) * 60

    key = _cache_key(
        'document_ids',
        origin=transport['from'],
        date=transport['date'],
        return_date=transport['return_date'],
        min_departure=transport['min_departure'],
        max_return=transport['max_return'],
        max_duration=transport['max_duration'],
        document_type=document_type,
        max_duration_seconds=max_duration_seconds,
    )

    cached = _cache_get(key)
    if cached is not None:
        return cached

    isochrones = get_cached_isochrone_pair(transport)
    intersection_geom = isochrones['intersection_geom']
    intersection_geom_wkt = (
        _reproject_geojson_to_3857(intersection_geom) if intersection_geom else None
    )

    if document_type == 'route':
        sure_ids, unverifiable_ids = classify_routes_within_geometry(
            intersection_geom_wkt, max_duration_seconds
        )
    else:
        sure_ids = get_waypoint_ids_within_geometry(intersection_geom_wkt)
        unverifiable_ids = set()
    document_ids = {
        'ids': sorted(sure_ids),
        'unverifiable_ids': sorted(unverifiable_ids),
    }

    if isochrones['aller_geom'] and isochrones['retour_geom']:
        _cache_set(key, document_ids, TRANSPORT_DOCUMENT_IDS_CACHE_TTL)

    return document_ids


def validate_transport_isochrones_params(request, **kwargs):
    """Validate the parameters of the transport isochrones route."""
    try:
        request.validated['transport'] = parse_transport_params(request.params)
    except ValueError as exc:
        request.errors.add('querystring', 'transport', str(exc))


def read_transport_isochrones(request):
    """Return the isochrones of a transport search as GeoJSON.

    Returns the aller (departure-anchored) and retour (arrival-anchored)
    isochrones of a transport search, and their intersection, as
    GeoJSON geometries (empty if they could not be computed).

    The documents are filtered with the same parameters, prefixed with
    `transport_`, on the routes and waypoints listings (see
    document.collection_get): this route is used to show the
    isochrones, and to check a search before using it as a filter. Both
    share the same cache, so that the isochrones are computed once.
    """
    isochrones = get_cached_isochrone_pair(request.validated['transport'])

    return {
        'aller_geom': isochrones['aller_geom'] or '',
        'retour_geom': isochrones['retour_geom'] or '',
        'intersection_geom': isochrones['intersection_geom'] or '',
    }


def _resolve_waypoint_journey_target(waypoint_json):
    """Resolve a waypoint's coordinates and Navitia coverage.

    Resolve a waypoint's journey target from its JSON geometry: its
    (lon, lat) in EPSG:4326 (the waypoint's geometry is stored in
    EPSG:3857) and the Navitia coverage that contains it.

    Shared by is_wp_journey_reachable (aller-only check) and
    is_wp_round_trip_reachable (aller + retour check).
    """
    geom = shape(json.loads(waypoint_json.get('geometry').get('geom')))

    src_epsg = 3857
    transformer = Transformer.from_crs(f'EPSG:{src_epsg}', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)

    destination_coverage = get_coverage(lon, lat)

    return lon, lat, destination_coverage


def is_wp_journey_reachable(waypoint, journey_params):
    """Check with the Navitia journey API if a waypoint is reachable.

    Query the navitia Journey api and returns true
    if the waypoint is reachable (at least one journey has been found)
    NOTE : the journey's departure time has to be
    the same day as the datetime's day in journey_params.
    """
    # enhance journey params with the 'to' parameter,
    # from the waypoint geometry.
    lon, lat, destination_coverage = _resolve_waypoint_journey_target(waypoint)

    journey_params['to'] = f'{lon};{lat}'

    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    if destination_coverage:
        url = BASE_URL + f'/coverage/{destination_coverage}/journeys'
    else:
        url = BASE_URL + '/journeys'

    try:
        json_response = navitia_get(
            url,
            params=journey_params,
            headers={'Authorization': api_key},
        )
        # no_origin / no_destination
        if json_response is None:
            return False

        # Business logic only
        for journey in json_response.get('journeys', []):
            journey_day = int(journey['departure_date_time'][6:8])
            param_day = int(journey_params['datetime'][6:8])
            if journey_day == param_day:
                return True

        return False
    except Exception as e:
        if str(e) == 'no_solution':
            return False
        else:
            raise HTTPInternalServerError(e) from e


def _query_navitia_journeys(params, coverage):
    """Query the Navitia journeys API.

    Query the Navitia journeys API, scoped to `coverage` when given
    (falls back to the generic /journeys endpoint otherwise).
    Returns the parsed JSON response, or None if no journey was found
    ("no_solution").
    """
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    if coverage:
        url = BASE_URL + f'/coverage/{coverage}/journeys'
    else:
        url = BASE_URL + '/journeys'

    try:
        return navitia_get(
            url,
            params=params,
            headers={'Authorization': api_key},
        )
    except Exception as e:
        if str(e) == 'no_solution':
            return None
        raise HTTPInternalServerError(e) from e


def _parse_navitia_datetime(value):
    """Parse a Navitia 'YYYYMMDDTHHMMSS' datetime string."""
    # Navitia datetimes are local times of the coverage, without a zone
    return datetime.strptime(value, '%Y%m%dT%H%M%S')  # noqa: DTZ007


def _round_trip_max_workers():
    """Return the number of documents checked at once.

    Number of documents checked at once (NAVITIA_ROUND_TRIP_WORKERS).
    """
    try:
        return max(1, int(os.getenv('NAVITIA_ROUND_TRIP_WORKERS', '')))
    except ValueError:
        return ROUND_TRIP_DEFAULT_WORKERS


def resolve_round_trip_target(waypoint_json):
    """Resolve what the Navitia requests need about an access waypoint.

    Everything needed to query Navitia about an access waypoint (its
    coordinates and coverage), resolved once and from the database: the
    Navitia requests can then run in other threads without touching it.
    """
    lon, lat, coverage = _resolve_waypoint_journey_target(waypoint_json)
    return {
        'document_id': waypoint_json.get('document_id'),
        'lon': float(lon),
        'lat': float(lat),
        'coords': f'{lon};{lat}',
        'coverage': coverage,
    }


def _no_leg():
    return {'found': False, 'departure': None, 'arrival': None}


def _query_aller_leg(target, from_coords, date, min_departure):
    """Query the aller leg to an access waypoint.

    The aller leg to an access waypoint: the EARLIEST journey from
    `from_coords` departing at/after `date`+`min_departure`, on that day.
    """
    params = {
        'from': from_coords,
        'to': target['coords'],
        'datetime': _combine_date_and_time(date, min_departure),
        'datetime_represents': 'departure',
    }
    response = _query_navitia_journeys(params, target['coverage'])
    if response is None:
        return _no_leg()

    param_day = date.replace('-', '')[6:8]
    same_day_journeys = [
        journey
        for journey in response.get('journeys', [])
        if journey['departure_date_time'][6:8] == param_day
    ]
    if not same_day_journeys:
        return _no_leg()

    journey = min(same_day_journeys, key=lambda j: j['arrival_date_time'])
    return {
        'found': True,
        'departure': journey['departure_date_time'],
        'arrival': journey['arrival_date_time'],
    }


def _query_retour_leg(target, from_coords, date, max_return):
    """Query the retour leg from an access waypoint.

    The retour leg from an access waypoint: the LATEST journey back to
    `from_coords` arriving at/before `date`+`max_return`, on that day (`date`
    being the day of the retour, which can be later than the one of the aller).
    """
    params = {
        'from': target['coords'],
        'to': from_coords,
        'datetime': _combine_date_and_time(date, max_return),
        'datetime_represents': 'arrival',
    }
    # the waypoint is the departure point of the journey, so its coverage
    # is used as the source coverage
    response = _query_navitia_journeys(params, target['coverage'])
    if response is None:
        return _no_leg()

    param_day = date.replace('-', '')[6:8]
    same_day_journeys = [
        journey
        for journey in response.get('journeys', [])
        if journey['arrival_date_time'][6:8] == param_day
    ]
    if not same_day_journeys:
        return _no_leg()

    journey = max(same_day_journeys, key=lambda j: j['departure_date_time'])
    return {
        'found': True,
        'departure': journey['departure_date_time'],
        'arrival': journey['arrival_date_time'],
    }


def _query_round_trip_legs(
    target, from_coords, date, min_departure, max_return, return_date=None
):
    """Query the aller and retour legs of an access waypoint at once.

    The aller and retour legs of an access waypoint, requested at once. The
    aller is on `date`, the retour on `return_date` (`date` by default).
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        aller = executor.submit(
            _query_aller_leg, target, from_coords, date, min_departure
        )
        retour = executor.submit(
            _query_retour_leg, target, from_coords, return_date or date, max_return
        )
        return aller.result(), retour.result()


def _legs_compatible(aller, retour, hiking_duration_seconds):
    """Tell whether both legs leave enough time for the hike.

    True if both legs were found AND there is enough time between the
    arrival of the aller and the departure of the retour to fit
    `hiking_duration_seconds`.
    """
    if not (aller['found'] and retour['found']):
        return False

    available_seconds = (
        _parse_navitia_datetime(retour['departure'])
        - _parse_navitia_datetime(aller['arrival'])
    ).total_seconds()
    return available_seconds >= hiking_duration_seconds


def is_wp_round_trip_reachable(
    waypoint_json,
    from_coords,
    date,
    min_departure,
    max_return,
    hiking_duration_seconds,
    return_date=None,
):
    """Check both directions of a round trip to an access waypoint.

    Check both directions of a round trip to an access waypoint, using
    real Navitia timetables (unlike is_wp_journey_reachable, which only
    checks the aller leg):

    - aller: the EARLIEST journey from `from_coords` to the waypoint,
      departing at/after `date`+`min_departure`.
    - retour: the LATEST journey from the waypoint back to `from_coords`,
      that still arrives at/before `return_date`+`max_return` (`return_date`
      being `date` by default).

    `compatible` is True only if both legs were found AND there is
    enough time between the aller arrival and the retour departure to
    fit `hiking_duration_seconds`.

    Returns a structured dict (never a plain boolean):
        {"aller": {"found", "departure", "arrival"},
         "retour": {"found", "departure", "arrival"},
         "compatible": bool}
    """
    target = resolve_round_trip_target(waypoint_json)
    aller, retour = _query_round_trip_legs(
        target, from_coords, date, min_departure, max_return, return_date
    )

    return {
        'aller': aller,
        'retour': retour,
        'compatible': _legs_compatible(aller, retour, hiking_duration_seconds),
    }


def _get_access_waypoints_for_document(document_id, document_type):
    """Resolve the access waypoints of a document.

    Resolve the access waypoint(s) of a document:
    - for a waypoint document, itself, if its waypoint_type is 'access'
      (otherwise none)
    - for a route document, its associated waypoints of type 'access'.
    """
    if document_type == 'waypoint':
        wp = (
            DBSession.query(Waypoint)
            .filter(
                Waypoint.document_id == document_id, Waypoint.waypoint_type == 'access'
            )
            .first()
        )
        return [wp] if wp else []

    return (
        DBSession.query(Waypoint)
        .join(
            Association,
            or_(
                Waypoint.document_id == Association.child_document_id,
                Waypoint.document_id == Association.parent_document_id,
            ),
        )
        .filter(
            Waypoint.waypoint_type == 'access',
            or_(
                Association.parent_document_id == document_id,
                Association.child_document_id == document_id,
            ),
        )
        .distinct()
        .all()
    )


def _resolve_hiking_duration_seconds(hiking_duration_param, document_id, document_type):
    """Resolve the hiking duration used as the round-trip time budget.

    Resolve the hiking duration (in seconds) to use as the round-trip
    time budget:
    - the explicit `hiking_duration` param (minutes) if given
    - otherwise, for a route, its own duration (see route_duration_days:
      the calculated duration, or the shortest of the declared durations,
      both in DAYS), converted to seconds, or None if the route has none
      (its duration is unknown: it cannot be checked)
    - otherwise (waypoint), 0.
    """
    if hiking_duration_param:
        return int(hiking_duration_param) * 60

    if document_type == 'route':
        route = DBSession.query(Route).filter(Route.document_id == document_id).first()
        if route is None:
            return 0
        duration = route_duration_days(route.calculated_duration, route.durations)
        # the duration is in DAYS: convert to SECONDS
        return duration * 86400 if duration is not None else None

    return 0


def _is_one_way_route(document_id):
    """Tell whether a route is done one way.

    Whether a route is done one way (a traverse...): the way back then
    starts from another access waypoint than the one reached by the aller.
    """
    route = DBSession.query(Route).filter(Route.document_id == document_id).first()
    return bool(
        route is not None
        and route.route_types
        and any(route_type in ONE_WAY_ROUTE_TYPES for route_type in route.route_types)
    )


def _sort_targets_by_distance(targets, from_coords):
    """Sort access waypoints, the closest first.

    The closest access waypoints first: they are the most likely to be
    reachable, which lets the check stop sooner.
    """
    from_lon, from_lat = (float(part) for part in from_coords.split(';'))
    scale = math.cos(math.radians(from_lat))

    return sorted(
        targets,
        key=lambda target: math.hypot(
            (target['lon'] - from_lon) * scale, target['lat'] - from_lat
        ),
    )


def prepare_round_trip_document(
    document_id, document_type, from_coords, hiking_duration_param
):
    """Read from the database what the round trip check of a document needs.

    It is done before the check, in the thread of the request or of the job: the Navitia
    requests themselves do not use the database, and can run in other threads.
    """
    access_waypoints = _get_access_waypoints_for_document(document_id, document_type)

    targets = [
        resolve_round_trip_target(to_json_dict(wp, waypoint_schema))
        for wp in access_waypoints
    ]

    return {
        'targets': _sort_targets_by_distance(targets, from_coords),
        'hiking_duration_seconds': _resolve_hiking_duration_seconds(
            hiking_duration_param, document_id, document_type
        ),
        'one_way': document_type == 'route' and _is_one_way_route(document_id),
    }


def _round_trip_result(aller, aller_target, retour, retour_target, compatible):
    return {
        'aller': aller,
        'retour': retour,
        'compatible': compatible,
        # the access waypoints the aller reaches and the retour leaves from:
        # different ones for a traverse
        'aller_waypoint_id': aller_target['document_id'] if aller['found'] else None,
        'retour_waypoint_id': retour_target['document_id'] if retour['found'] else None,
    }


def _best_same_waypoint_result(
    targets,
    from_coords,
    date,
    min_departure,
    max_return,
    hiking_duration_seconds,
    return_date=None,
):
    """Check an out-and-back round trip.

    For an out-and-back route (or a waypoint): the retour leaves from the
    access waypoint the aller reached. The check stops at the first access
    waypoint where it works, otherwise the best result is the one with the
    most legs (aller/retour) found.
    """

    def legs_found(result):
        return int(result['aller']['found']) + int(result['retour']['found'])

    best = None
    for target in targets:
        aller, retour = _query_round_trip_legs(
            target, from_coords, date, min_departure, max_return, return_date
        )
        result = _round_trip_result(
            aller,
            target,
            retour,
            target,
            _legs_compatible(aller, retour, hiking_duration_seconds),
        )

        if result['compatible']:
            return result
        if best is None or legs_found(result) > legs_found(best):
            best = result

    return best


def _best_one_way_result(
    targets,
    from_coords,
    date,
    min_departure,
    max_return,
    hiking_duration_seconds,
    return_date=None,
):
    """For a traverse: arrive by an access waypoint, leave from another one.

    Every aller leg is combined with every retour leg found, the check stops at the
    first working pair, otherwise the best result is the earliest aller with the latest
    retour.
    """
    alleres = []
    retours = []

    for target in targets:
        aller, retour = _query_round_trip_legs(
            target, from_coords, date, min_departure, max_return, return_date
        )
        if aller['found']:
            alleres.append((aller, target))
        if retour['found']:
            retours.append((retour, target))

        for aller_leg, aller_target in alleres:
            for retour_leg, retour_target in retours:
                if _legs_compatible(aller_leg, retour_leg, hiking_duration_seconds):
                    return _round_trip_result(
                        aller_leg, aller_target, retour_leg, retour_target, True
                    )

    aller, aller_target = min(
        alleres, key=lambda item: item[0]['arrival'], default=(_no_leg(), targets[0])
    )
    retour, retour_target = max(
        retours, key=lambda item: item[0]['departure'], default=(_no_leg(), targets[0])
    )
    return _round_trip_result(aller, aller_target, retour, retour_target, False)


def best_round_trip_result(
    prepared, from_coords, date, min_departure, max_return, return_date=None
):
    """Check the round trip of a document over all its access waypoints.

    The round trip check of a document prepared by
    prepare_round_trip_document, using real Navitia timetables, over all
    its access waypoints. The retour is on `return_date` (`date` by default).

    A document of an unknown duration (no explicit hiking duration, and a
    route without calculated nor declared duration) is not checked, no
    Navitia request is made: `{'compatible': None, 'duration_unknown': True}`.
    """
    targets = prepared['targets']
    if not targets:
        return _round_trip_result(_no_leg(), {}, _no_leg(), {}, False)

    if prepared['hiking_duration_seconds'] is None:
        return {'compatible': None, 'duration_unknown': True}

    check = _best_one_way_result if prepared['one_way'] else _best_same_waypoint_result
    return check(
        targets,
        from_coords,
        date,
        min_departure,
        max_return,
        prepared['hiking_duration_seconds'],
        return_date,
    )


def validate_round_trip_reachable_params(request, **kwargs):
    """Validate the parameters of the single-item round-trip check.

    Validates the required parameters for the single-item round trip
    reachable verification route.
    """
    required_params = [
        'document_id',
        'document_type',
        'from',
        'date',
        'min_departure',
        'max_return',
    ]

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')

    document_type = request.params.get('document_type')
    if document_type is not None and document_type not in ('route', 'waypoint'):
        request.errors.add(
            'querystring',
            'document_type',
            "document_type must be 'route' or 'waypoint'",
        )

    _validate_transport_window_param(request)


def read_round_trip_reachable(request):
    """Check the round-trip reachability of one route or waypoint.

    Synchronous, single-item round-trip (aller + retour) reachability
    check for one route or waypoint, using real Navitia timetables.
    Resolves the document's access waypoint(s) and returns the best
    result across them (see best_round_trip_result) : at most a
    handful of Navitia calls, so no job/redis machinery is needed.
    The optional `return_date` is the day of the retour (the day of the
    aller by default).
    """
    params = request.params
    document_id = int(params.get('document_id'))
    document_type = params.get('document_type')
    from_coords = params.get('from')
    date = params.get('date')
    min_departure = params.get('min_departure')
    max_return = params.get('max_return')
    return_date = params.get('return_date') or None
    hiking_duration_param = params.get('hiking_duration')

    prepared = prepare_round_trip_document(
        document_id, document_type, from_coords, hiking_duration_param
    )

    return best_round_trip_result(
        prepared, from_coords, date, min_departure, max_return, return_date
    )


def get_navitia_isochrone(isochrone_params):
    """
    Query the navitia Isochrones api, and returns the isochrone object.

    When 'from' is provided, this computes a departure-anchored
    "reachable from" isochrone (Navitia ignores 'to' in that case).
    When 'from' is absent and 'to' is provided instead, this computes an
    arrival-anchored "reachable to" isochrone. The source coverage is
    resolved from whichever of 'from'/'to' is present.
    """
    coord_param = isochrone_params.get('from') or isochrone_params.get('to')
    lon = coord_param.split(';')[0]
    lat = coord_param.split(';')[1]
    source_coverage = get_coverage(lon, lat)

    # Retrieve navitia API Key from env var
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    if not source_coverage:
        raise HTTPInternalServerError('Coverage not found for source')

    return navitia_get(
        BASE_URL + f'/coverage/{source_coverage}/isochrones',
        params=isochrone_params,
        headers={'Authorization': api_key},
    )


def is_wp_in_isochrone(waypoint, isochrone_geom):
    """Return true if waypoints is contained in isochrone_geom."""
    # get lon & lat
    geom = shape(json.loads(waypoint.get('geometry').get('geom')))

    src_epsg = 3857
    transformer = Transformer.from_crs(f'EPSG:{src_epsg}', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)
    pt = Point(lon, lat)

    return isochrone_geom.contains(pt)


def extract_meta_params(request):
    """Extract meta parameters such as offset, limit and lang."""
    v = request.validated
    return {
        'offset': 0,
        'limit': 2000,
        'lang': v.get('lang'),
    }


def extract_journey_params(request):
    """Extract parameters for journey query."""
    return {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'datetime_represents': request.params.get('datetime_represents'),
        'walking_speed': request.params.get('walking_speed'),
        'max_walking_duration_to_pt': request.params.get('max_walking_duration_to_pt'),
        'to': '',
    }


def _clamp_boundary_duration_seconds(duration_seconds):
    """Clamp a boundary duration between the trip duration limits.

    Clamp a boundary duration (in seconds) between MIN_TRIP_DURATION and
    MAX_TRIP_DURATION (both expressed in minutes).
    """
    return max(min(duration_seconds, MAX_TRIP_DURATION * 60), MIN_TRIP_DURATION * 60)


def extract_isochrone_params(request):
    """
    Extract parameters for isochrone query.

    NOTE : the boundary duration is bounded by constants
        MAX_TRIP_DURATION and MIN_TRIP_DURATION
    if the boundary duration goes beyond limits,
        it is set to the limit it goes past.
    """
    params = {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'boundary_duration[]': request.params.get('boundary_duration'),
        'datetime_represents': request.params.get('datetime_represents'),
    }
    # normalize boundary
    bd = params['boundary_duration[]']
    if len(bd.split(',')) == 1:
        params['boundary_duration[]'] = _clamp_boundary_duration_seconds(int(bd))
    else:
        # default is max trip duration
        params['boundary_duration[]'] = MAX_TRIP_DURATION * 60
    return params


def _combine_date_and_time(date_str, time_str):
    """Combine a date and a time into a Navitia datetime.

    Combine a 'YYYY-MM-DD' date and a 'HH:MM' time into the compact
    'YYYYMMDDTHHMMSS' datetime format expected by the Navitia API.
    """
    compact_date = date_str.replace('-', '')
    compact_time = time_str.replace(':', '')
    return f'{compact_date}T{compact_time}00'


def _minutes_between(start_hhmm, end_hhmm):
    """Return the number of minutes between two 'HH:MM' times.

    NOTE: this does not handle a window crossing midnight (end_hhmm < start_hhmm); such
    a case would yield a negative value. See _window_minutes for a window over
    several days.
    """
    start_h, start_m = (int(part) for part in start_hhmm.split(':'))
    end_h, end_m = (int(part) for part in end_hhmm.split(':'))
    return (end_h * 60 + end_m) - (start_h * 60 + start_m)


def _window_minutes(date, min_departure, return_date, max_return):
    """Return the number of minutes of a transport window.

    The window goes from `date`+`min_departure` (the aller) to
    `return_date`+`max_return` (the retour, `date` if `return_date` is empty).
    """
    start = datetime.strptime(  # noqa: DTZ007 (local times, compared together)
        f'{date} {min_departure}', '%Y-%m-%d %H:%M'
    )
    end = datetime.strptime(  # noqa: DTZ007
        f'{return_date or date} {max_return}', '%Y-%m-%d %H:%M'
    )
    return int((end - start).total_seconds() // 60)


def _transport_window_minutes(transport):
    """Return the number of minutes of the window of a parsed transport search."""
    return _window_minutes(
        transport['date'],
        transport['min_departure'],
        transport['return_date'],
        transport['max_return'],
    )


def _check_return_date(date, return_date):
    """Check the date of the retour: a valid date, not before the aller's."""
    try:
        parsed_date = datetime.strptime(date, '%Y-%m-%d')  # noqa: DTZ007
    except ValueError as e:
        raise ValueError("'date' must be formatted as 'YYYY-MM-DD'") from e
    try:
        parsed_return_date = datetime.strptime(return_date, '%Y-%m-%d')  # noqa: DTZ007
    except ValueError as e:
        raise ValueError("'return_date' must be formatted as 'YYYY-MM-DD'") from e
    if parsed_return_date < parsed_date:
        raise ValueError("'return_date' must not be before 'date'")


def _validate_transport_window_param(request):
    """Validate the dates and times of the round trip check requests.

    The same checks as a transport search (see check_transport_window): the
    round trip checks call Navitia too.
    """
    params = request.params
    if not params.get('date'):
        # reported as missing
        return

    try:
        check_transport_window(
            params['date'],
            params.get('min_departure'),
            params.get('max_return'),
            params.get('return_date'),
        )
    except ValueError as exc:
        request.errors.add('querystring', 'transport', str(exc))


def _extract_isochrone_shape(isochrone_response):
    """Return the geometry of the first isochrone of a response.

    Return the shapely geometry of the first isochrone found in a Navitia
    isochrones response, or None if the response has no isochrone.
    """
    if not isochrone_response:
        return None
    isochrones = isochrone_response.get('isochrones', [])
    if not isochrones:
        return None
    return shape(isochrones[0]['geojson'])


def _reproject_geojson_to_3857(geojson):
    """Reproject a GeoJSON geometry to EPSG:3857 as WKT.

    Reproject a GeoJSON geometry (as returned by the Navitia isochrones
    API, in EPSG:4326) to EPSG:3857 (the SRID used by
    DocumentGeometry.geom), and return it as a WKT string.
    """
    geom_4326 = shape(geojson)
    transformer = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)
    geom_3857 = shapely_transform(transformer.transform, geom_4326)
    return geom_3857.wkt


def _resolve_boundary_duration_seconds(
    min_departure, max_return, override_duration_minutes=None, window_minutes=None
):
    """Return the boundary duration of the isochrones of a window.

    The boundary duration of the isochrones of a transport window: the
    override if given, otherwise derived from the (min_departure, max_return)
    window; in both cases clamped between MIN_TRIP_DURATION and
    MAX_TRIP_DURATION.
    """
    if override_duration_minutes is not None:
        return _clamp_boundary_duration_seconds(override_duration_minutes * 60)

    if window_minutes is None:
        window_minutes = _minutes_between(min_departure, max_return)
    return _clamp_boundary_duration_seconds(window_minutes * 60)


def get_navitia_isochrone_pair(
    from_coords,
    date,
    min_departure,
    max_return,
    override_duration_minutes=None,
    return_date=None,
):
    """Compute the isochrones of a round-trip transport search.

    Compute the pair of isochrones needed to check round-trip
    transport-accessibility from/to `from_coords` within the
    [min_departure, max_return] window on `date`:
    - aller_geom: reachable FROM from_coords, anchored at departure
      (date + min_departure)
    - retour_geom: reachable TO from_coords, anchored at arrival
      (return_date + max_return, `date` if there is no return_date)
    - intersection_geom: their intersection (only the area reachable
      both ways within the window is relevant).

    The boundary duration used for both isochrones is
    override_duration_minutes if given, otherwise derived from the
    (min_departure, max_return) window; in both cases it is clamped
    between MIN_TRIP_DURATION and MAX_TRIP_DURATION.

    Returns a dict {aller_geom, retour_geom, intersection_geom}, each a
    GeoJSON-like dict (from shapely.geometry.mapping), or None when the
    corresponding isochrone (or the intersection) could not be computed.
    """
    boundary_duration_seconds = _resolve_boundary_duration_seconds(
        min_departure,
        max_return,
        override_duration_minutes,
        window_minutes=_window_minutes(date, min_departure, return_date, max_return),
    )

    aller_params = {
        'from': from_coords,
        'datetime': _combine_date_and_time(date, min_departure),
        'datetime_represents': 'departure',
        'boundary_duration[]': boundary_duration_seconds,
    }
    retour_params = {
        'to': from_coords,
        'datetime': _combine_date_and_time(return_date or date, max_return),
        'datetime_represents': 'arrival',
        'boundary_duration[]': boundary_duration_seconds,
    }

    aller_shape = _extract_isochrone_shape(get_navitia_isochrone(aller_params))
    retour_shape = _extract_isochrone_shape(get_navitia_isochrone(retour_params))

    intersection_geom = None
    if aller_shape is not None and retour_shape is not None:
        intersection_geom = mapping(aller_shape.intersection(retour_shape))

    return {
        'aller_geom': mapping(aller_shape) if aller_shape is not None else None,
        'retour_geom': mapping(retour_shape) if retour_shape is not None else None,
        'intersection_geom': intersection_geom,
    }


def collect_areas_from_results(results, area_index):
    """Load the areas referenced in the results by document_id.

    Extract all area document_ids from results, load Area objects from DB,
    and return {document_id: Area}.
    """
    area_ids = set()

    for row in results:
        areas = row[area_index]

        if not areas:
            continue

        for area in areas:
            doc_id = area.get('document_id')
            if doc_id:
                area_ids.add(doc_id)

    area_objects = DBSession.query(Area).filter(Area.document_id.in_(area_ids)).all()

    return {a.document_id: a for a in area_objects}


def collect_waypoints_from_results(results):
    """Load the waypoints referenced in the results by document_id.

    Extract all waypoint document_ids from results,
    load Waypoint objects from DB,
    and return {document_id: Waypoint}.
    """
    wp_ids = set()

    for _, _, waypoints in results:
        if not waypoints:
            continue

        for wp in waypoints:
            doc_id = wp.get('document_id')
            if doc_id:
                wp_ids.add(doc_id)

    wp_objects = (
        DBSession.query(Waypoint).filter(Waypoint.document_id.in_(wp_ids)).all()
    )

    return {wp for wp in wp_objects}


def handle_navitia_response(response):
    """Handle Navitia HTTP errors and returns parsed JSON on success.

    Raises HTTP* exceptions otherwise.
    """
    if response.status_code == 400:
        raise HTTPBadRequest('invalid_param')

    elif response.status_code == 401:
        raise HTTPUnauthorized('auth_error')

    elif response.status_code == 404:
        raise HTTPNotFound(response.json()['error']['id'])

    elif response.status_code == 500:
        raise HTTPInternalServerError('navitia_internal_error')

    elif not response.ok:
        raise HTTPInternalServerError('unknown_error')

    return response.json()


# The Navitia key is paid per request: the calls the API makes are counted
# per day (UTC) in Redis, and refused over a daily budget. Only the calls
# made count, not the answers of the cache. The budget and the kill switch
# are environment variables, as the key.
NAVITIA_DAILY_BUDGET_DEFAULT = 5000
# a warning is logged when this share of the budget is used
NAVITIA_BUDGET_WARNING_SHARE = 0.8
# the stable text of the log lines the Grafana alert counts
NAVITIA_BUDGET_LOG_MARKER = 'NAVITIA_BUDGET'


def _navitia_daily_budget():
    try:
        return int(os.getenv('NAVITIA_DAILY_BUDGET', NAVITIA_DAILY_BUDGET_DEFAULT))
    except ValueError:
        return NAVITIA_DAILY_BUDGET_DEFAULT


def _navitia_enabled():
    value = os.getenv('NAVITIA_ENABLED', 'true').strip().lower()
    return value not in ('0', 'false', 'no', 'off')


def consume_navitia_budget():
    """Count a call to Navitia, or raise a 503 when it must not be made.

    Refused when NAVITIA_ENABLED is false (the kill switch), when the calls
    of the day reached NAVITIA_DAILY_BUDGET, or when they cannot be counted
    (Redis unavailable): the cost comes first.
    """
    if not _navitia_enabled():
        raise HTTPServiceUnavailable('navitia_disabled')

    budget = _navitia_daily_budget()
    day = datetime.now(ZoneInfo('UTC')).date()
    key = f'navitia:calls:{day.isoformat()}'
    try:
        r = _cache_client()
        count = r.incr(key)
        if count == 1:
            # kept a little longer than the day, to be read afterwards
            r.expire(key, 2 * 86400)
    except redis.RedisError as e:
        log.error(
            '%s: the Navitia calls cannot be counted, refused',
            NAVITIA_BUDGET_LOG_MARKER,
        )
        raise HTTPServiceUnavailable('navitia_budget_unavailable') from e

    # each threshold is logged once a day, by the call that crosses it
    if count == int(budget * NAVITIA_BUDGET_WARNING_SHARE):
        log.warning(
            '%s: %d Navitia calls today, %d%% of the daily budget (%d)',
            NAVITIA_BUDGET_LOG_MARKER,
            count,
            NAVITIA_BUDGET_WARNING_SHARE * 100,
            budget,
        )
    if count > budget:
        if count == budget + 1:
            log.error(
                '%s: daily budget of %d Navitia calls reached, the calls are refused '
                'until the end of the day (UTC)',
                NAVITIA_BUDGET_LOG_MARKER,
                budget,
            )
        raise HTTPServiceUnavailable('navitia_budget_exceeded')


def navitia_get(url, *, params=None, headers=None, timeout=30):
    consume_navitia_budget()
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return handle_navitia_response(response)

    except HTTPException:
        # the errors of Navitia (e.g. 404 no_solution), with their status
        raise

    except requests.exceptions.Timeout as e:
        raise HTTPInternalServerError('Timeout when calling the Navitia API') from e

    except requests.exceptions.RequestException as e:
        raise HTTPInternalServerError(str(e)) from e

    except Exception as e:
        raise HTTPInternalServerError(str(e)) from e


def configure_jobs_redis(settings):
    """Connect the jobs to the Redis of the settings (redis.url, redis.db_jobs)."""
    global _jobs_redis_pool, _cache_redis_pool
    url = '{}?db={}'.format(settings['redis.url'], settings.get('redis.db_jobs', 0))
    _jobs_redis_pool = redis.ConnectionPool.from_url(url)
    # the cache of the transport searches, in the same database: short
    # timeouts, as a search still works (slower) without it
    _cache_redis_pool = redis.ConnectionPool.from_url(
        url, socket_connect_timeout=1, socket_timeout=2
    )


def _set_job_value(r, job_id, name, value):
    """Store a value of a job, which expires after JOB_TTL."""
    r.set(f'job:{job_id}:{name}', value, ex=JOB_TTL)


def redis_client():
    """Return a client of the Redis of the jobs."""
    if _jobs_redis_pool is None:
        raise RuntimeError('configure_jobs_redis was not called')
    return redis.Redis(connection_pool=_jobs_redis_pool)


def start_job_background(target, request):
    """Start a job in the background.

    Start a job in the background,
    target is the query function to execute in bg
    request is the request to pass to the function.
    """
    # each job makes many calls to Navitia: a process runs a few at once only
    if not _running_jobs.acquire(blocking=False):
        # the UI retries once, after the delay it reads in the message
        raise HTTPTooManyRequests(
            f'Too many searches are running: retry after {JOB_RETRY_AFTER} seconds'
        )
    try:
        job_id = str(uuid.uuid4())
        r = redis_client()
        _set_job_value(r, job_id, 'progress', 0)
        _set_job_value(r, job_id, 'status', 'running')

        def run():
            try:
                target(job_id, request)
            finally:
                _running_jobs.release()

        threading.Thread(target=run, daemon=True).start()
    except BaseException:
        _running_jobs.release()
        raise
    return {'job_id': job_id}


def _end_thread_db_session():
    """
    Release the database session used by a background job thread.

    `DBSession` is a scoped session, so each job thread gets its own session
    and connection. The request session (web.db) only covers the request
    thread, so the job has to end its transaction and remove its session
    itself; otherwise the connection stays checked out of the pool (possibly
    "idle in transaction") for the lifetime of the worker process.

    The jobs only read from the database, so the transaction is aborted
    (rolled back) rather than committed.
    """
    try:
        DBSession.rollback()
    except Exception:
        log.exception('Error aborting background job transaction')
    finally:
        DBSession.remove()


def get_job_status(r, job_id):
    """Return the ongoing job status."""
    status = r.get(f'job:{job_id}:status')
    if status is None:
        return None, {'error': 'unknown_job_id'}
    status = status.decode()
    return status, status


def read_result_from_redis(r, job_id):
    """Return the result from redis."""
    status = r.get(f'job:{job_id}:status')
    if status is None:
        return {'error': 'unknown_job_id'}
    status = status.decode()
    if status == 'running':
        return {'status': 'running'}
    if status == 'error':
        error = _read_job_error(r.get(f'job:{job_id}:error'))
        return {'status': 'error', 'message': error['message']}
    if status == 'done':
        data = r.get(f'job:{job_id}:result')
        if not data:
            return {'status': 'error', 'message': 'missing_result'}
        return {'status': 'done', 'result': json.loads(data)}
    return {'error': 'unknown_status', 'status': status}


def _event_stream(events):
    """Answer the events of a generator as a stream (text/event-stream)."""
    return StreamingResponse(events, media_type='text/event-stream; charset=UTF-8')


async def progress_stream(
    r, job_id, poll_interval=0.5, max_duration=STREAM_MAX_DURATION
):
    """Yield the job progress, until the job ends, is unknown or takes too long."""
    # The stream must end: an unknown job id (or a job whose values expired,
    # e.g. lost with its worker) ends it at once, and so does a job running
    # for longer than max_duration. An async generator: on a uvicorn worker,
    # the reads borrow one of its threads (server.threads) for a moment, and
    # the wait holds none. A sync one held a thread for the whole stream: a
    # few searches at once blocked every other request of the worker (#2448).
    deadline = time.monotonic() + max_duration
    while True:
        events, ended = await to_thread.run_sync(_progress_events, r, job_id)
        for event in events:
            yield event
        if ended:
            break

        if time.monotonic() >= deadline:
            yield _error_event('timeout', 'The job takes too long')
            break

        await anyio.sleep(poll_interval)


def _progress_events(r, job_id):
    """Return the events of the job progress, and whether the stream ends."""
    raw_progress = r.get(f'job:{job_id}:progress')
    raw_found = r.get(f'job:{job_id}:found')
    raw_not_found = r.get(f'job:{job_id}:not_found')
    raw_total = r.get(f'job:{job_id}:total')
    status = r.get(f'job:{job_id}:status')

    if status is None:
        return [_error_event('unknown_job', f'Unknown job {job_id}')], True

    progress = int(raw_progress) if raw_progress is not None else 0
    found = int(raw_found) if raw_found is not None else 0
    not_found = int(raw_not_found) if raw_not_found is not None else 0
    total = int(raw_total) if raw_total is not None else 0

    payload = {
        'progress': progress,
        'total': total,
        'found': found,
        'not_found': not_found,
    }
    events = [(f'data: {json.dumps(payload)}\n\n').encode()]

    if status.decode() == 'done':
        events.append(b'event: done\ndata: done\n\n')
        return events, True
    elif status.decode() == 'error':
        error = _read_job_error(r.get(f'job:{job_id}:error'))
        events.append(_error_event(error['id'], error['message']))
        return events, True
    return events, False


def _job_error(exc):
    """Return the error of a failed job, as the UI reads them: id and message."""
    # a single word is an error id of Navitia (e.g. date_out_of_bounds), which
    # the UI may translate; it shows the message of the others
    message = str(exc)
    error_id = message if re.fullmatch(r'\w+', message) else 'job_error'
    return {'id': error_id, 'message': message}


def _read_job_error(raw):
    """Return the stored error of a job (JSON; a plain message before)."""
    if raw is None:
        return {'id': 'job_error', 'message': 'unknown error'}
    try:
        error = json.loads(raw)
    except ValueError:
        error = None
    if isinstance(error, dict) and 'id' in error and 'message' in error:
        return error
    return {'id': 'job_error', 'message': raw.decode(errors='replace')}


def _error_event(error_id, message):
    """Return an error event of the progress stream, as the UI reads them."""
    data = json.dumps({'id': error_id, 'message': message})
    return (f'event: error\ndata: {data}\n\n').encode()


def _store_job_progress(r, job_id, count, found, not_found):
    """Store the progress of a job.

    Store job progress which is :
    progress : the number of queries done
    found : the number of successful queries
    not_found: the number of unsuccessful queries.
    """
    _set_job_value(r, job_id, 'progress', count)
    _set_job_value(r, job_id, 'found', found)
    _set_job_value(r, job_id, 'not_found', not_found)
    r.publish(f'job:{job_id}:events', f'progress:{count}')
    r.publish(f'job:{job_id}:events', f'found:{found}')
    r.publish(f'job:{job_id}:events', f'not_found:{not_found}')
