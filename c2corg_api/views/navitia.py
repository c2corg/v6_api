import hashlib
import json
import logging
import math
import os
import requests
import redis
import uuid
import time
import re
import threading
import ast
import transaction
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from sqlalchemy import or_
from c2corg_api.models import DBSession
from c2corg_api.models.area import Area
from c2corg_api.models.association import Association
from c2corg_api.models.waypoint import Waypoint, schema_waypoint
from c2corg_api.views.coverage import get_coverage
from c2corg_api.views.waypoint import (
    build_reachable_waypoints_query,
    get_waypoint_ids_within_geometry,
)
from c2corg_api.views.route import (
    build_reachable_route_query_with_waypoints,
    get_route_ids_within_geometry,
)
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform as shapely_transform
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnauthorized,
)
from pyramid.response import Response
from cornice.resource import resource, view
from c2corg_api.views import cors_policy, to_json_dict
from c2corg_api.models.route import schema_route, Route
from c2corg_api.models.area import schema_listing_area
from pyproj import Transformer


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

# redis to store job's value (progress, result, error...)
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 0

BASE_URL = 'https://api.navitia.io/v1'


def validate_navitia_params(request, **kwargs):
    """Validates the required parameters for the Navitia API"""
    required_params = ['from', 'to', 'datetime', 'datetime_represents']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, 'Parameter %s required' % param)


@resource(path='/navitia/journeys', cors_policy=cors_policy)
class NavitiaRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_navitia_params])
    def get(self):
        """
        Endpoint to retrieve trips from the Navitia API

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
    """Validates the required parameters for the journey reachable doc route"""
    required_params = [
        'from',
        'datetime',
        'datetime_represents',
        'walking_speed',
        'max_walking_duration_to_pt',
    ]

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, 'Parameter %s required' % param)


@resource(path='/navitia/journeyreachableroutes/start', cors_policy=cors_policy)
class StartNavitiaJourneyReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """
        start job to retrieve journey reachable routes
        returns job id
        """
        return start_job_background(compute_journey_reachable_routes, self.request)


@resource(path='/navitia/journeyreachablewaypoints/start', cors_policy=cors_policy)
class StartNavitiaJourneyReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """
        start job to retrieve journey reachable waypoints
        returns job id
        """
        return start_job_background(compute_journey_reachable_waypoints, self.request)


@resource(
    path='/navitia/journeyreachableroutes/result/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyReachableRoutesResultRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """
        get the result of the job : get journey reachable routes
        returns the result
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
        """
        get the result of the job : get journey reachable waypoints
        returns the result
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
        """
        monitor progress of job id for journey reachable routes
        """
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
        """
        monitor progress of job id for journey reachable waypoints
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return Response(
            app_iter=progress_stream(r, job_id), content_type='text/event-stream'
        )


def validate_round_trip_batch_params(request, **kwargs):
    """Validates the required parameters for the round-trip batch
    verification jobs (an explicit shortlist of document ids, plus the
    same temporal parameters used for a single-item check)"""
    required_params = ['ids', 'from', 'date', 'min_departure', 'max_return']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, 'Parameter %s required' % param)


@resource(path='/navitia/journeyroundtriproutes/start', cors_policy=cors_policy)
class StartNavitiaJourneyRoundTripRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_round_trip_batch_params])
    def get(self):
        """
        start job to verify round-trip (aller + retour) reachability for
        an explicit shortlist of route ids
        returns job id
        """
        return start_job_background(compute_round_trip_reachable_routes, self.request)


@resource(path='/navitia/journeyroundtripwaypoints/start', cors_policy=cors_policy)
class StartNavitiaJourneyRoundTripWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_round_trip_batch_params])
    def get(self):
        """
        start job to verify round-trip (aller + retour) reachability for
        an explicit shortlist of waypoint ids
        returns job id
        """
        return start_job_background(
            compute_round_trip_reachable_waypoints, self.request
        )


@resource(
    path='/navitia/journeyroundtriproutes/result/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyRoundTripRoutesResultRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """
        get the result of the job : verify round-trip reachable routes
        returns the result
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return read_result_from_redis(r, job_id)


@resource(
    path='/navitia/journeyroundtripwaypoints/result/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyRoundTripWaypointsResultRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """
        get the result of the job : verify round-trip reachable waypoints
        returns the result
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return read_result_from_redis(r, job_id)


@resource(
    path='/navitia/journeyroundtriproutes/progress/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyRoundTripRoutesProgressRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """
        monitor progress of job id for round-trip reachable routes
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return Response(
            app_iter=progress_stream(r, job_id), content_type='text/event-stream'
        )


@resource(
    path='/navitia/journeyroundtripwaypoints/progress/{job_id}', cors_policy=cors_policy
)
class NavitiaJourneyRoundTripWaypointsProgressRest:
    def __init__(self, request, context=None):
        self.request = request

    @view()
    def get(self):
        """
        monitor progress of job id for round-trip reachable waypoints
        """
        r = redis_client()
        job_id = self.request.matchdict.get('job_id')
        return Response(
            app_iter=progress_stream(r, job_id), content_type='text/event-stream'
        )


def compute_journey_reachable_routes(job_id, request):
    """
    Get all waypoints matching filters in params, that are reachable
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
        r.set('job:%s:total' % job_id, total)

        count = found = not_found = 0
        navitia_wp_map = {}

        for wp in wp_objects:
            result = is_wp_journey_reachable(
                to_json_dict(wp, schema_waypoint), journey_params
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
                    json_areas.append(to_json_dict(area_obj, schema_listing_area))
            route.areas = json_areas
            routes.append(to_json_dict(route, schema_route, True))

        r.set(
            'job:%s:result' % job_id,
            json.dumps({'documents': routes, 'total': len(routes)}),
        )
        r.set('job:%s:status' % job_id, 'done')
    except Exception as exc:
        log.exception(str(exc))
        r.set('job:%s:status' % job_id, 'error')
        r.set('job:%s:error' % job_id, str(exc))
    finally:
        _end_thread_db_session()


def compute_journey_reachable_waypoints(job_id, request):
    """
    Get all routes matching filters in params, that are reachable
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
        r.set('job:%s:total' % job_id, total)

        count = found = not_found = 0
        waypoints = []

        for waypoint, areas in results:
            count += 1
            r.publish('job:%s:events' % job_id, 'not_found:%d' % not_found)
            reachable = is_wp_journey_reachable(
                to_json_dict(waypoint, schema_waypoint), journey_params
            )
            if reachable:
                found += 1
                json_areas = []
                for area in areas or []:
                    area_obj = areas_map.get(area.get('document_id'))
                    if area_obj:
                        json_areas.append(to_json_dict(area_obj, schema_listing_area))
                waypoint.areas = json_areas
                waypoints.append(to_json_dict(waypoint, schema_waypoint, True))
            else:
                not_found += 1
            _store_job_progress(r, job_id, count, found, not_found)

        r.set(
            'job:%s:result' % job_id,
            json.dumps({'documents': waypoints, 'total': len(waypoints)}),
        )
        r.set('job:%s:status' % job_id, 'done')
    except Exception as exc:
        log.exception('Error computing reachable waypoints')
        r.set('job:%s:status' % job_id, 'error')
        r.set('job:%s:error' % job_id, str(exc))
    finally:
        _end_thread_db_session()


def _compute_round_trip_reachable(
    job_id, request, document_type, too_many_error_message
):
    """
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
        hiking_duration_param = request.GET.get('hiking_duration')

        total = len(ids)
        log.info('Number of round-trip verifications : %d', total)
        r.set('job:%s:total' % job_id, total)

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

        r.set(
            'job:%s:result' % job_id, json.dumps({'results': results, 'total': total})
        )
        r.set('job:%s:status' % job_id, 'done')
    except Exception as exc:
        log.exception(str(exc))
        r.set('job:%s:status' % job_id, 'error')
        r.set('job:%s:error' % job_id, str(exc))
    finally:
        _end_thread_db_session()


def compute_round_trip_reachable_routes(job_id, request):
    """
    Verify round-trip (aller + retour) reachability for an explicit
    shortlist of route ids (see _compute_round_trip_reachable).
    the result can be found inside redis
    """
    _compute_round_trip_reachable(
        job_id,
        request,
        'route',
        "Couldn't proceed with computation : Too much routes found.",
    )


def compute_round_trip_reachable_waypoints(job_id, request):
    """
    Verify round-trip (aller + retour) reachability for an explicit
    shortlist of waypoint ids (see _compute_round_trip_reachable).
    the result can be found inside redis
    """
    _compute_round_trip_reachable(
        job_id,
        request,
        'waypoint',
        "Couldn't proceed with computation : Too much waypoints found.",
    )


def validate_isochrone_reachable_params(request, **kwargs):
    """Validates the required parameters
    for the isochrone reachable doc route"""
    required_params = ['from', 'datetime', 'datetime_represents', 'boundary_duration']

    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, 'Parameter %s required' % param)


@resource(path='/navitia/isochronesreachableroutes', cors_policy=cors_policy)
class NavitiaIsochronesReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_isochrone_reachable_params])
    def get(self):
        """
        Get all routes matching filters in params, that have at least
        one waypoint of type access that is inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func
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
                        to_json_dict(wp, schema_waypoint), isochrone_geom
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
                                    to_json_dict(area_obj, schema_listing_area)
                                )

                        # assign JSON areas to the waypoint
                        route.areas = json_areas
                        route_dict = to_json_dict(route, schema_route, True)
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
        """
        Get all waypoints matching filters in params,
        that are inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func
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
                        to_json_dict(waypoint, schema_waypoint), isochrone_geom
                    ):
                        json_areas = []
                        if areas is None:
                            areas = []

                        for area in areas:
                            area_obj = areas_map.get(area.get('document_id'))
                            if area_obj:
                                json_areas.append(
                                    to_json_dict(area_obj, schema_listing_area)
                                )

                        # assign JSON areas to the waypoint
                        waypoint.areas = json_areas
                        wp_dict = to_json_dict(waypoint, schema_waypoint, True)
                        waypoints.append(wp_dict)

            return {
                'documents': waypoints,
                'total': len(waypoints),
                'isochron_geom': geojson,
            }
        except Exception as e:
            return json.dumps(str(e))


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


def normalize_transport_from(from_coords):
    """
    Returns the 'lon;lat' starting point rounded to
    TRANSPORT_COORDINATE_DECIMALS, or raises a ValueError if it is invalid.
    """
    try:
        lon_str, lat_str = from_coords.split(';')
        lon, lat = float(lon_str), float(lat_str)
    except AttributeError, ValueError:
        raise ValueError("'from' must be formatted as 'longitude;latitude'")

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("'from' is not a valid coordinate")

    return '%.*f;%.*f' % (
        TRANSPORT_COORDINATE_DECIMALS,
        lon,
        TRANSPORT_COORDINATE_DECIMALS,
        lat,
    )


def _parse_positive_int(name, value):
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError("'%s' must be an integer" % name)
    if number < 0:
        raise ValueError("'%s' must not be negative" % name)
    return number


def parse_transport_params(params, prefix=''):
    """
    Validate and normalize the transport search parameters found in `params`
    (the query string), where each name is preceded by `prefix`:
    from ('lon;lat'), date ('YYYY-MM-DD'), min_departure and max_return
    ('HH:MM'), and the optional max_duration and hiking_duration (minutes).

    Returns a dict with those keys (the optional ones being None when not
    given), or raises a ValueError describing the problem.
    """
    missing = [
        prefix + name
        for name in ('from', 'date', 'min_departure', 'max_return')
        if not params.get(prefix + name)
    ]
    if missing:
        raise ValueError('Parameter %s required' % ', '.join(missing))

    date = params.get(prefix + 'date')
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        raise ValueError("'date' must be formatted as 'YYYY-MM-DD'")

    times = {}
    for name in ('min_departure', 'max_return'):
        value = params.get(prefix + name)
        if not _TIME_PATTERN.match(value):
            raise ValueError("'%s' must be formatted as 'HH:MM'" % name)
        times[name] = value

    if _minutes_between(times['min_departure'], times['max_return']) <= 0:
        raise ValueError("'max_return' must be after 'min_departure'")

    return {
        'from': normalize_transport_from(params.get(prefix + 'from')),
        'date': date,
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
    """redis client for the cache: a missing redis must not slow requests"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        socket_connect_timeout=1,
        socket_timeout=2,
    )


def _cache_key(kind, **parts):
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode('utf-8'))
    return 'transport:%s:%s' % (kind, digest.hexdigest())


def _cache_get(key):
    """returns the cached value, or None if missing or if redis fails"""
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
    """
    The aller/retour/intersection isochrones of a transport search (see
    get_navitia_isochrone_pair), computed once per search.
    """
    boundary_duration = _resolve_boundary_duration_seconds(
        transport['min_departure'], transport['max_return'], transport['max_duration']
    )
    key = _cache_key(
        'isochrones',
        origin=transport['from'],
        date=transport['date'],
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
    )

    # an incomplete result can be a temporary failure: do not keep it
    if isochrones['aller_geom'] and isochrones['retour_geom']:
        _cache_set(key, isochrones, TRANSPORT_ISOCHRONES_CACHE_TTL)

    return isochrones


def get_cached_transport_document_ids(transport, document_type):
    """
    The ids of the routes or waypoints (depending on `document_type`) having
    an access waypoint within the intersection of the aller and retour
    isochrones of a transport search.
    """
    max_duration_seconds = None
    if document_type == 'route' and transport['hiking_duration']:
        # A precise budget would be
        # (max_return - min_departure) - transit_time_estimate,
        # but transit time is only known per-candidate (it would
        # require a Navitia journey call per route). As a first
        # cut / acceptable approximation, use the full transport
        # window as the max allowed Route.calculated_duration.
        max_duration_seconds = (
            _minutes_between(transport['min_departure'], transport['max_return']) * 60
        )

    key = _cache_key(
        'document_ids',
        origin=transport['from'],
        date=transport['date'],
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
        document_ids = get_route_ids_within_geometry(
            intersection_geom_wkt, max_duration_seconds
        )
    else:
        document_ids = get_waypoint_ids_within_geometry(intersection_geom_wkt)
    document_ids = sorted(document_ids)

    if isochrones['aller_geom'] and isochrones['retour_geom']:
        _cache_set(key, document_ids, TRANSPORT_DOCUMENT_IDS_CACHE_TTL)

    return document_ids


def validate_transport_isochrones_params(request, **kwargs):
    """Validates the parameters of the transport isochrones route"""
    try:
        request.validated['transport'] = parse_transport_params(request.params)
    except ValueError as exc:
        request.errors.add('querystring', 'transport', str(exc))


@resource(path='/navitia/transportisochrones', cors_policy=cors_policy)
class NavitiaTransportIsochronesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_transport_isochrones_params])
    def get(self):
        """
        Returns the aller (departure-anchored) and retour (arrival-anchored)
        isochrones of a transport search, and their intersection, as
        GeoJSON geometries (empty if they could not be computed).

        The documents are filtered with the same parameters, prefixed with
        `transport_`, on the routes and waypoints listings (see
        DocumentRest._collection_get): this route is used to show the
        isochrones, and to check a search before using it as a filter. Both
        share the same cache, so that the isochrones are computed once.
        """
        isochrones = get_cached_isochrone_pair(self.request.validated['transport'])

        return {
            'aller_geom': isochrones['aller_geom'] or '',
            'retour_geom': isochrones['retour_geom'] or '',
            'intersection_geom': isochrones['intersection_geom'] or '',
        }


def _resolve_waypoint_journey_target(waypoint_json):
    """
    Resolve a waypoint's journey target from its JSON geometry: its
    (lon, lat) in EPSG:4326 (the waypoint's geometry is stored in
    EPSG:3857) and the Navitia coverage that contains it.

    Shared by is_wp_journey_reachable (aller-only check) and
    is_wp_round_trip_reachable (aller + retour check).
    """
    geom = shape(json.loads(waypoint_json.get('geometry').get('geom')))

    src_epsg = 3857
    transformer = Transformer.from_crs(
        'EPSG:%d' % src_epsg, 'EPSG:4326', always_xy=True
    )
    lon, lat = transformer.transform(geom.x, geom.y)

    destination_coverage = get_coverage(lon, lat)

    return lon, lat, destination_coverage


def is_wp_journey_reachable(waypoint, journey_params):
    """
    Query the navitia Journey api and returns true
    if the waypoint is reachable (at least one journey has been found)
    NOTE : the journey's departure time has to be
    the same day as the datetime's day in journey_params
    """
    # enhance journey params with the 'to' parameter,
    # from the waypoint geometry.
    lon, lat, destination_coverage = _resolve_waypoint_journey_target(waypoint)

    journey_params['to'] = '%s;%s' % (lon, lat)

    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    if destination_coverage:
        url = BASE_URL + '/coverage/%s/journeys' % destination_coverage
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
            raise HTTPInternalServerError(e)


def _query_navitia_journeys(params, coverage):
    """
    Query the Navitia journeys API, scoped to `coverage` when given
    (falls back to the generic /journeys endpoint otherwise).
    Returns the parsed JSON response, or None if no journey was found
    ("no_solution").
    """
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPInternalServerError('Navitia API config is missing')

    if coverage:
        url = BASE_URL + '/coverage/%s/journeys' % coverage
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
        raise HTTPInternalServerError(e)


def _parse_navitia_datetime(value):
    """Parse a Navitia 'YYYYMMDDTHHMMSS' datetime string."""
    return datetime.strptime(value, '%Y%m%dT%H%M%S')


def _round_trip_max_workers():
    """Number of documents checked at once (NAVITIA_ROUND_TRIP_WORKERS)"""
    try:
        return max(1, int(os.getenv('NAVITIA_ROUND_TRIP_WORKERS', '')))
    except ValueError:
        return ROUND_TRIP_DEFAULT_WORKERS


def resolve_round_trip_target(waypoint_json):
    """
    Everything needed to query Navitia about an access waypoint (its
    coordinates and coverage), resolved once and from the database: the
    Navitia requests can then run in other threads without touching it.
    """
    lon, lat, coverage = _resolve_waypoint_journey_target(waypoint_json)
    return {
        'document_id': waypoint_json.get('document_id'),
        'lon': float(lon),
        'lat': float(lat),
        'coords': '%s;%s' % (lon, lat),
        'coverage': coverage,
    }


def _no_leg():
    return {'found': False, 'departure': None, 'arrival': None}


def _query_aller_leg(target, from_coords, date, min_departure):
    """
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
    """
    The retour leg from an access waypoint: the LATEST journey back to
    `from_coords` arriving at/before `date`+`max_return`, on that day.
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


def _query_round_trip_legs(target, from_coords, date, min_departure, max_return):
    """The aller and retour legs of an access waypoint, requested at once."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        aller = executor.submit(
            _query_aller_leg, target, from_coords, date, min_departure
        )
        retour = executor.submit(
            _query_retour_leg, target, from_coords, date, max_return
        )
        return aller.result(), retour.result()


def _legs_compatible(aller, retour, hiking_duration_seconds):
    """
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
    waypoint_json, from_coords, date, min_departure, max_return, hiking_duration_seconds
):
    """
    Check both directions of a round trip to an access waypoint, using
    real Navitia timetables (unlike is_wp_journey_reachable, which only
    checks the aller leg):

    - aller: the EARLIEST journey from `from_coords` to the waypoint,
      departing at/after `date`+`min_departure`.
    - retour: the LATEST journey from the waypoint back to `from_coords`,
      that still arrives at/before `date`+`max_return`.

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
        target, from_coords, date, min_departure, max_return
    )

    return {
        'aller': aller,
        'retour': retour,
        'compatible': _legs_compatible(aller, retour, hiking_duration_seconds),
    }


def _get_access_waypoints_for_document(document_id, document_type):
    """
    Resolve the access waypoint(s) of a document:
    - for a waypoint document, itself, if its waypoint_type is 'access'
      (otherwise none)
    - for a route document, its associated waypoints of type 'access'
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
    """
    Resolve the hiking duration (in seconds) to use as the round-trip
    time budget:
    - the explicit `hiking_duration` param (minutes) if given
    - otherwise, for a route, its own calculated_duration (stored in
      DAYS, see Route.calculated_duration), converted to seconds
    - otherwise (waypoint, or route without a calculated_duration), 0
    """
    if hiking_duration_param:
        return int(hiking_duration_param) * 60

    if document_type == 'route':
        route = DBSession.query(Route).filter(Route.document_id == document_id).first()
        if route is not None and route.calculated_duration is not None:
            # calculated_duration is stored in DAYS: convert to SECONDS
            return route.calculated_duration * 86400

    return 0


def _is_one_way_route(document_id):
    """
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
    """
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
    """
    Reads from the database what the round trip check of a document needs.
    It is done before the check, in the thread of the request or of the job:
    the Navitia requests themselves do not use the database, and can run in
    other threads.
    """
    access_waypoints = _get_access_waypoints_for_document(document_id, document_type)

    targets = [
        resolve_round_trip_target(to_json_dict(wp, schema_waypoint))
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
    targets, from_coords, date, min_departure, max_return, hiking_duration_seconds
):
    """
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
            target, from_coords, date, min_departure, max_return
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
    targets, from_coords, date, min_departure, max_return, hiking_duration_seconds
):
    """
    For a traverse: arrive by an access waypoint, leave from another one.
    Every aller leg is combined with every retour leg found, the check
    stops at the first working pair, otherwise the best result is the
    earliest aller with the latest retour.
    """
    alleres = []
    retours = []

    for target in targets:
        aller, retour = _query_round_trip_legs(
            target, from_coords, date, min_departure, max_return
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


def best_round_trip_result(prepared, from_coords, date, min_departure, max_return):
    """
    The round trip check of a document prepared by
    prepare_round_trip_document, using real Navitia timetables, over all
    its access waypoints.
    """
    targets = prepared['targets']
    if not targets:
        return _round_trip_result(_no_leg(), {}, _no_leg(), {}, False)

    check = _best_one_way_result if prepared['one_way'] else _best_same_waypoint_result
    return check(
        targets,
        from_coords,
        date,
        min_departure,
        max_return,
        prepared['hiking_duration_seconds'],
    )


def validate_round_trip_reachable_params(request, **kwargs):
    """Validates the required parameters for the single-item round trip
    reachable verification route"""
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
            request.errors.add('querystring', param, 'Parameter %s required' % param)

    document_type = request.params.get('document_type')
    if document_type is not None and document_type not in ('route', 'waypoint'):
        request.errors.add(
            'querystring',
            'document_type',
            "document_type must be 'route' or 'waypoint'",
        )


@resource(path='/navitia/roundtripreachable', cors_policy=cors_policy)
class NavitiaRoundTripReachableRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_round_trip_reachable_params])
    def get(self):
        """
        Synchronous, single-item round-trip (aller + retour) reachability
        check for one route or waypoint, using real Navitia timetables.
        Resolves the document's access waypoint(s) and returns the best
        result across them (see best_round_trip_result) : at most a
        handful of Navitia calls, so no job/redis machinery is needed.
        """
        params = self.request.params
        document_id = int(params.get('document_id'))
        document_type = params.get('document_type')
        from_coords = params.get('from')
        date = params.get('date')
        min_departure = params.get('min_departure')
        max_return = params.get('max_return')
        hiking_duration_param = params.get('hiking_duration')

        prepared = prepare_round_trip_document(
            document_id, document_type, from_coords, hiking_duration_param
        )

        return best_round_trip_result(
            prepared, from_coords, date, min_departure, max_return
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
        BASE_URL + '/coverage/%s/isochrones' % source_coverage,
        params=isochrone_params,
        headers={'Authorization': api_key},
    )


def is_wp_in_isochrone(waypoint, isochrone_geom):
    """
    Returns true if waypoints is contained in isochrone_geom
    """
    # get lon & lat
    geom = shape(json.loads(waypoint.get('geometry').get('geom')))

    src_epsg = 3857
    transformer = Transformer.from_crs(
        'EPSG:%d' % src_epsg, 'EPSG:4326', always_xy=True
    )
    lon, lat = transformer.transform(geom.x, geom.y)
    pt = Point(lon, lat)

    return isochrone_geom.contains(pt)


def extract_meta_params(request):
    """
    Extract meta parameters such as offset, limit and lang
    """
    v = request.validated
    return {
        'offset': 0,
        'limit': 2000,
        'lang': v.get('lang'),
    }


def extract_journey_params(request):
    """
    Extract parameters for journey query
    """
    return {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'datetime_represents': request.params.get('datetime_represents'),
        'walking_speed': request.params.get('walking_speed'),
        'max_walking_duration_to_pt': request.params.get('max_walking_duration_to_pt'),
        'to': '',
    }


def _clamp_boundary_duration_seconds(duration_seconds):
    """
    Clamp a boundary duration (in seconds) between MIN_TRIP_DURATION and
    MAX_TRIP_DURATION (both expressed in minutes).
    """
    return max(min(duration_seconds, MAX_TRIP_DURATION * 60), MIN_TRIP_DURATION * 60)


def extract_isochrone_params(request):
    """
    Extract parameters for isochrone query

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
    """
    Combine a 'YYYY-MM-DD' date and a 'HH:MM' time into the compact
    'YYYYMMDDTHHMMSS' datetime format expected by the Navitia API.
    """
    compact_date = date_str.replace('-', '')
    compact_time = time_str.replace(':', '')
    return '%sT%s00' % (compact_date, compact_time)


def _minutes_between(start_hhmm, end_hhmm):
    """
    Return the number of minutes between two 'HH:MM' times.
    NOTE: this does not handle a window crossing midnight
    (end_hhmm < start_hhmm); such a case would yield a negative value.
    """
    start_h, start_m = (int(part) for part in start_hhmm.split(':'))
    end_h, end_m = (int(part) for part in end_hhmm.split(':'))
    return (end_h * 60 + end_m) - (start_h * 60 + start_m)


def _extract_isochrone_shape(isochrone_response):
    """
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
    """
    Reproject a GeoJSON geometry (as returned by the Navitia isochrones
    API, in EPSG:4326) to EPSG:3857 (the SRID used by
    DocumentGeometry.geom), and return it as a WKT string.
    """
    geom_4326 = shape(geojson)
    transformer = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)
    geom_3857 = shapely_transform(transformer.transform, geom_4326)
    return geom_3857.wkt


def _resolve_boundary_duration_seconds(
    min_departure, max_return, override_duration_minutes=None
):
    """
    The boundary duration of the isochrones of a transport window: the
    override if given, otherwise derived from the (min_departure, max_return)
    window; in both cases clamped between MIN_TRIP_DURATION and
    MAX_TRIP_DURATION.
    """
    if override_duration_minutes is not None:
        return _clamp_boundary_duration_seconds(override_duration_minutes * 60)

    window_minutes = _minutes_between(min_departure, max_return)
    return _clamp_boundary_duration_seconds(window_minutes * 60)


def get_navitia_isochrone_pair(
    from_coords, date, min_departure, max_return, override_duration_minutes=None
):
    """
    Compute the pair of isochrones needed to check round-trip
    transport-accessibility from/to `from_coords` within the
    [min_departure, max_return] window on `date`:
    - aller_geom: reachable FROM from_coords, anchored at departure
      (date + min_departure)
    - retour_geom: reachable TO from_coords, anchored at arrival
      (date + max_return)
    - intersection_geom: their intersection (only the area reachable
      both ways within the window is relevant)

    The boundary duration used for both isochrones is
    override_duration_minutes if given, otherwise derived from the
    (min_departure, max_return) window; in both cases it is clamped
    between MIN_TRIP_DURATION and MAX_TRIP_DURATION.

    Returns a dict {aller_geom, retour_geom, intersection_geom}, each a
    GeoJSON-like dict (from shapely.geometry.mapping), or None when the
    corresponding isochrone (or the intersection) could not be computed.
    """
    boundary_duration_seconds = _resolve_boundary_duration_seconds(
        min_departure, max_return, override_duration_minutes
    )

    aller_params = {
        'from': from_coords,
        'datetime': _combine_date_and_time(date, min_departure),
        'datetime_represents': 'departure',
        'boundary_duration[]': boundary_duration_seconds,
    }
    retour_params = {
        'to': from_coords,
        'datetime': _combine_date_and_time(date, max_return),
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
    """
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
    """
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
    """
    Handles Navitia HTTP errors and returns parsed JSON on success.
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

    except requests.exceptions.Timeout:
        raise HTTPInternalServerError('Timeout when calling the Navitia API')

    except requests.exceptions.RequestException as e:
        raise HTTPInternalServerError(str(e))

    except Exception as e:
        raise HTTPInternalServerError(str(e))


def redis_client():
    """fast way to get redis client"""
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)


def start_job_background(target, request):
    """start a job in the background,
    target is the query function to execute in bg
    request is the request to pass to the function"""
    job_id = str(uuid.uuid4())
    r = redis_client()
    r.set('job:%s:progress' % job_id, 0)
    r.set('job:%s:status' % job_id, 'running')
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
    """returns the ongoing job status"""
    status = r.get('job:%s:status' % job_id)
    if status is None:
        return None, {'error': 'unknown_job_id'}
    status = status.decode()
    return status, status


def read_result_from_redis(r, job_id):
    """returns the result from redis"""
    status = r.get('job:%s:status' % job_id)
    if status is None:
        return {'error': 'unknown_job_id'}
    status = status.decode()
    if status == 'running':
        return {'status': 'running'}
    if status == 'error':
        error_msg = r.get('job:%s:error' % job_id)
        return {
            'status': 'error',
            'message': error_msg.decode() if error_msg else 'unknown error',
        }
    if status == 'done':
        data = r.get('job:%s:result' % job_id)
        if not data:
            return {'status': 'error', 'message': 'missing_result'}
        return {'status': 'done', 'result': json.loads(data)}
    return {'error': 'unknown_status', 'status': status}


def progress_stream(r, job_id, poll_interval=0.5):
    """yield the job progress"""
    while True:
        raw_progress = r.get('job:%s:progress' % job_id)
        raw_found = r.get('job:%s:found' % job_id)
        raw_not_found = r.get('job:%s:not_found' % job_id)
        raw_total = r.get('job:%s:total' % job_id)

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
        yield ('data: %s\n\n' % json.dumps(payload)).encode('utf-8')

        status = r.get('job:%s:status' % job_id)
        if status and status.decode() == 'done':
            yield b'event: done\ndata: done\n\n'
            break
        elif status and status.decode() == 'error':
            payload = r.get('job:%s:error' % job_id)
            json_payload = json.dumps(ast.literal_eval(payload.decode()))
            yield ('event: error\ndata: %s\n\n' % json_payload).encode('utf-8')
            break

        time.sleep(poll_interval)


def _store_job_progress(r, job_id, count, found, not_found):
    """
    store job progress which is :
    progress : the number of queries done
    found : the number of successful queries
    not_found: the number of unsuccessful queries
    """
    r.set('job:%s:progress' % job_id, count)
    r.set('job:%s:found' % job_id, found)
    r.set('job:%s:not_found' % job_id, not_found)
    r.publish('job:%s:events' % job_id, 'progress:%d' % count)
    r.publish('job:%s:events' % job_id, 'found:%d' % found)
    r.publish('job:%s:events' % job_id, 'not_found:%d' % not_found)
