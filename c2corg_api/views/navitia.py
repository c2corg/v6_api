import json
import logging
import os
import re
import threading
import time
import uuid

import redis
import requests
import transaction
from cornice.resource import resource, view
from pyproj import Transformer
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnauthorized,
)
from pyramid.response import Response
from shapely.geometry import Point, shape

from c2corg_api.models import DBSession
from c2corg_api.models.area import Area
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.schemas.area import area_listing_schema
from c2corg_api.schemas.route import route_schema
from c2corg_api.schemas.waypoint import waypoint_schema
from c2corg_api.views import cors_policy, to_json_dict
from c2corg_api.views.coverage import get_coverage
from c2corg_api.views.route import build_reachable_route_query_with_waypoints
from c2corg_api.views.waypoint import build_reachable_waypoints_query

log = logging.getLogger(__name__)

# When editing these constants, make sure to edit them in the front too
# (itinevert-service)
MAX_ROUTE_THRESHOLD = 50
MAX_TRIP_DURATION = 240
MIN_TRIP_DURATION = 20

# redis to store job's value (progress, result, error...): see
# configure_jobs_redis
_jobs_redis_pool = None
# the values of a job expire after its last write: long enough for the UI to
# read the result of a finished job
JOB_TTL = 3600  # seconds
# the longest a progress stream follows a job
STREAM_MAX_DURATION = 600  # seconds

BASE_URL = 'https://api.navitia.io/v1'


def validate_navitia_params(request, **kwargs):
    """Validate the required parameters for the Navitia API."""
    required_params = ['from', 'to', 'datetime', 'datetime_represents']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')


@resource(path='/navitia/journeys', cors_policy=cors_policy)
class NavitiaRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_navitia_params])
    def get(self):
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
            'from': self.request.params.get('from'),
            'to': self.request.params.get('to'),
            'datetime': self.request.params.get('datetime'),
            'datetime_represents': self.request.params.get('datetime_represents'),
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
            if param in self.request.params:
                params[param] = self.request.params.get(param)

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


@resource(path='/navitia/journeyreachableroutes/start', cors_policy=cors_policy)
class StartNavitiaJourneyReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """Start a job finding the journey-reachable routes, return its id."""
        return start_job_background(compute_journey_reachable_routes, self.request)


@resource(path='/navitia/journeyreachablewaypoints/start', cors_policy=cors_policy)
class StartNavitiaJourneyReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """Start a job finding the journey-reachable waypoints, return its id."""
        return start_job_background(compute_journey_reachable_waypoints, self.request)


@resource(
    path='/navitia/journeyreachableroutes/result/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyReachableRoutesResultRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """Get the result of a reachable-routes job.

        Get the result of the job : get journey reachable routes
        returns the result.
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return read_result_from_redis(r, job_id)


@resource(
    path='/navitia/journeyreachablewaypoints/result/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyReachableWaypointsResultRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """Get the result of a reachable-waypoints job.

        Get the result of the job : get journey reachable waypoints
        returns the result.
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return read_result_from_redis(r, job_id)


@resource(
    path='/navitia/journeyreachableroutes/progress/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyReachableRoutesProgressRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """Monitor progress of job id for journey reachable routes."""
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return Response(
            app_iter=progress_stream(r, job_id), content_type='text/event-stream'
        )


@resource(
    path='/navitia/journeyreachablewaypoints/progress/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyReachableWaypointsProgressRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """Monitor progress of job id for journey reachable waypoints."""
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return Response(
            app_iter=progress_stream(r, job_id), content_type='text/event-stream'
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
        results = query.all()

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


def validate_isochrone_reachable_params(request, **kwargs):
    """Validate the required parameters for the isochrone reachable doc route."""
    required_params = ['from', 'datetime', 'datetime_represents', 'boundary_duration']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Parameter {param} required')


@resource(path='/navitia/isochronesreachableroutes', cors_policy=cors_policy)
class NavitiaIsochronesReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_isochrone_reachable_params])
    def get(self):
        """Get the routes with an access waypoint inside the isochron.

        Get all routes matching filters in params, that have at least
        one waypoint of type access that is inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func.
        """
        try:
            meta_params = extract_meta_params(self.request)

            isochrone_params = extract_isochrone_params(self.request)

            query, _ = build_reachable_route_query_with_waypoints(
                self.request.GET, meta_params
            )

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
                                json_areas.append(
                                    to_json_dict(area_obj, area_listing_schema)
                                )

                        # assign JSON areas to the waypoint
                        route.areas = json_areas
                        route_dict = to_json_dict(route, route_schema, True)
                        routes.append(route_dict)

            return {'documents': routes, 'total': len(routes), 'isochron_geom': geojson}
        except Exception as e:
            return json.dumps(str(e))


@resource(path='/navitia/isochronesreachablewaypoints', cors_policy=cors_policy)
class NavitiaIsochronesReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_isochrone_reachable_params])
    def get(self):
        """Get the waypoints inside the isochron.

        Get all waypoints matching filters in params,
        that are inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func.
        """
        try:
            meta_params = extract_meta_params(self.request)

            isochrone_params = extract_isochrone_params(self.request)

            query, _ = build_reachable_waypoints_query(self.request.GET, meta_params)

            results = query.all()

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
                                json_areas.append(
                                    to_json_dict(area_obj, area_listing_schema)
                                )

                        # assign JSON areas to the waypoint
                        waypoint.areas = json_areas
                        wp_dict = to_json_dict(waypoint, waypoint_schema, True)
                        waypoints.append(wp_dict)

            return {
                'documents': waypoints,
                'total': len(waypoints),
                'isochron_geom': geojson,
            }
        except Exception as e:
            return json.dumps(str(e))


def is_wp_journey_reachable(waypoint, journey_params):
    """Check with the Navitia journey API if a waypoint is reachable.

    Query the navitia Journey api and returns true
    if the waypoint is reachable (at least one journey has been found)
    NOTE : the journey's departure time has to be
    the same day as the datetime's day in journey_params.
    """
    # enhance journey params with the 'to' parameter,
    # from the waypoint geometry.
    geom = shape(json.loads(waypoint.get('geometry').get('geom')))

    src_epsg = 3857
    transformer = Transformer.from_crs(f'EPSG:{src_epsg}', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)

    journey_params['to'] = f'{lon};{lat}'

    destination_coverage = get_coverage(lon, lat)

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


def get_navitia_isochrone(isochrone_params):
    """Query the navitia Isochrones api, and returns the isochrone object."""
    lon = isochrone_params.get('from').split(';')[0]
    lat = isochrone_params.get('from').split(';')[1]
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
        duration = int(bd)
        params['boundary_duration[]'] = max(
            min(duration, MAX_TRIP_DURATION * 60), MIN_TRIP_DURATION * 60
        )
    else:
        # default is max trip duration
        params['boundary_duration[]'] = MAX_TRIP_DURATION * 60
    return params


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


def navitia_get(url, *, params=None, headers=None, timeout=30):
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return handle_navitia_response(response)

    except requests.exceptions.Timeout as e:
        raise HTTPInternalServerError('Timeout when calling the Navitia API') from e

    except requests.exceptions.RequestException as e:
        raise HTTPInternalServerError(str(e)) from e

    except Exception as e:
        raise HTTPInternalServerError(str(e)) from e


def configure_jobs_redis(settings):
    """Connect the jobs to the Redis of the settings (redis.url, redis.db_jobs)."""
    global _jobs_redis_pool
    url = '{}?db={}'.format(settings['redis.url'], settings.get('redis.db_jobs', 0))
    _jobs_redis_pool = redis.ConnectionPool.from_url(url)


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
    job_id = str(uuid.uuid4())
    r = redis_client()
    _set_job_value(r, job_id, 'progress', 0)
    _set_job_value(r, job_id, 'status', 'running')
    threading.Thread(target=target, args=(job_id, request), daemon=True).start()
    return {'job_id': job_id}


def _end_thread_db_session():
    """
    Release the database session used by a background job thread.

    `DBSession` is a scoped session, so each job thread gets its own session
    and connection. pyramid_tm only manages the request thread, so the job
    has to end its transaction and remove its session itself; otherwise the
    connection stays checked out of the pool (possibly "idle in
    transaction") for the lifetime of the worker process.

    The jobs only read from the database, so the transaction is aborted
    (rolled back) rather than committed.
    """
    try:
        # `DBSession` is registered with zope.sqlalchemy: the session joined
        # this thread's transaction manager, so abort that transaction. This
        # rolls back and closes the session.
        transaction.abort()
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


def progress_stream(r, job_id, poll_interval=0.5, max_duration=STREAM_MAX_DURATION):
    """Yield the job progress, until the job ends, is unknown or takes too long."""
    # The stream holds a worker of the server: it must end. An unknown job id
    # (or a job whose values expired, e.g. lost with its worker) ends it at
    # once, and so does a job running for longer than max_duration.
    deadline = time.monotonic() + max_duration
    while True:
        raw_progress = r.get(f'job:{job_id}:progress')
        raw_found = r.get(f'job:{job_id}:found')
        raw_not_found = r.get(f'job:{job_id}:not_found')
        raw_total = r.get(f'job:{job_id}:total')
        status = r.get(f'job:{job_id}:status')

        if status is None:
            yield _error_event('unknown_job', f'Unknown job {job_id}')
            break

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
        yield (f'data: {json.dumps(payload)}\n\n').encode()

        if status.decode() == 'done':
            yield b'event: done\ndata: done\n\n'
            break
        elif status.decode() == 'error':
            error = _read_job_error(r.get(f'job:{job_id}:error'))
            yield _error_event(error['id'], error['message'])
            break

        if time.monotonic() >= deadline:
            yield _error_event('timeout', 'The job takes too long')
            break

        time.sleep(poll_interval)


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
