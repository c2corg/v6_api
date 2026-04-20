"""
Pure helpers for Navitia (public-transport) integration.

Extracted from ``c2corg_api.views.navitia`` so that the FastAPI router
has no dependency on ``views/``.
"""

import ast
import json
import os
import threading
import time
import uuid

import redis
import requests
from c2corg_api.models import DBSession
from fastapi import HTTPException
from pyproj import Transformer
from shapely.geometry import Point, shape

from c2corg_api.models.area import Area
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.routers.helpers.coverage import get_coverage

# Constants (keep in sync with the front-end itinevert-service)
MAX_ROUTE_THRESHOLD = 50
MAX_TRIP_DURATION = 240
MIN_TRIP_DURATION = 20

BASE_URL = 'https://api.navitia.io/v1'

REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 0


# ── Parameter extraction ─────────────────────────────────────


def extract_meta_params(request):
    """Extract meta parameters (offset, limit, lang)."""
    v = request.validated
    return {'offset': 0, 'limit': 2000, 'lang': v.get('lang')}


def extract_journey_params(request):
    """Extract parameters for a Navitia journey query."""
    return {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'datetime_represents': request.params.get('datetime_represents'),
        'walking_speed': request.params.get('walking_speed'),
        'max_walking_duration_to_pt': request.params.get('max_walking_duration_to_pt'),
        'to': '',
    }


def extract_isochrone_params(request):
    """Extract parameters for a Navitia isochrone query."""
    params = {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'boundary_duration[]': request.params.get('boundary_duration'),
        'datetime_represents': request.params.get('datetime_represents'),
    }
    bd = params['boundary_duration[]']
    if len(bd.split(',')) == 1:
        duration = int(bd)
        params['boundary_duration[]'] = max(
            min(duration, MAX_TRIP_DURATION * 60), MIN_TRIP_DURATION * 60
        )
    else:
        params['boundary_duration[]'] = MAX_TRIP_DURATION * 60
    return params


# ── Navitia API calls ────────────────────────────────────────


def get_navitia_isochrone(isochrone_params):
    """Query the Navitia Isochrones API."""
    lon = isochrone_params.get('from').split(';')[0]
    lat = isochrone_params.get('from').split(';')[1]
    source_coverage = get_coverage(lon, lat)

    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPException(500, 'Navitia API config is missing')

    if not source_coverage:
        raise HTTPException(500, 'Coverage not found for source')

    return navitia_get(
        BASE_URL + '/coverage/%s/isochrones' % source_coverage,
        params=isochrone_params,
        headers={'Authorization': api_key},
    )


def is_wp_journey_reachable(waypoint, journey_params):
    """Return True if *waypoint* is reachable via Navitia journeys."""
    geom = shape(json.loads(waypoint.get('geometry').get('geom')))

    transformer = Transformer.from_crs('EPSG:3857', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)
    journey_params['to'] = '%s;%s' % (lon, lat)

    destination_coverage = get_coverage(lon, lat)

    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPException(500, 'Navitia API config is missing')

    if destination_coverage:
        url = BASE_URL + '/coverage/%s/journeys' % destination_coverage
    else:
        url = BASE_URL + '/journeys'

    json_response = navitia_get(
        url, params=journey_params, headers={'Authorization': api_key}
    )

    if json_response is None:
        return False

    for journey in json_response.get('journeys', []):
        journey_day = int(journey['departure_date_time'][6:8])
        param_day = int(journey_params['datetime'][6:8])
        if journey_day == param_day:
            return True

    return False


def is_wp_in_isochrone(waypoint, isochrone_geom):
    """Return True if *waypoint* is inside *isochrone_geom*."""
    geom = shape(json.loads(waypoint.get('geometry').get('geom')))

    transformer = Transformer.from_crs('EPSG:3857', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)
    pt = Point(lon, lat)

    return isochrone_geom.contains(pt)


# ── Result-set helpers ───────────────────────────────────────


def collect_areas_from_results(results, area_index):
    """Load Area objects for all area IDs found in *results*."""
    area_ids = set()
    for row in results:
        areas = row[area_index]
        if not areas:
            continue
        for area in areas:
            doc_id = area.get('document_id')
            if doc_id:
                area_ids.add(doc_id)

    area_objects = (
        DBSession.query(Area).filter(Area.document_id.in_(area_ids)).all()
    )
    return {a.document_id: a for a in area_objects}


def collect_waypoints_from_results(results):
    """Load Waypoint objects for all waypoint IDs in *results*."""
    wp_ids = set()
    for _, _, waypoints in results:
        if not waypoints:
            continue
        for wp in waypoints:
            doc_id = wp.get('document_id')
            if doc_id:
                wp_ids.add(doc_id)

    return set(
        DBSession.query(Waypoint).filter(Waypoint.document_id.in_(wp_ids)).all()
    )


# ── HTTP helpers ─────────────────────────────────────────────


def handle_navitia_response(response):
    """Parse Navitia HTTP response, raising on errors."""
    if response.status_code == 401:
        raise HTTPException(500, 'Auth error with Navitia API')
    elif response.status_code == 400:
        raise HTTPException(400, 'Invalid params for Navitia API')
    elif response.status_code == 404:
        error_id = response.json().get('error', {}).get('id')
        if error_id in ('no_destination', 'no_origin'):
            return None
        raise HTTPException(500, response.json().get('error', {}))
    elif not response.ok:
        raise HTTPException(500, 'Navitia API error: %d' % response.status_code)
    return response.json()


def navitia_get(url, *, params=None, headers=None, timeout=30):
    """GET wrapper for the Navitia API."""
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        return handle_navitia_response(response)
    except requests.exceptions.Timeout:
        raise HTTPException(500, 'Timeout calling Navitia API')
    except requests.exceptions.RequestException as e:
        raise HTTPException(500, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Redis / background job helpers ───────────────────────────


def redis_client():
    """Return a Redis client."""
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)


def start_job_background(target, request):
    """Start *target* in a background thread, returning a job ID."""
    job_id = str(uuid.uuid4())
    r = redis_client()
    r.set('job:%s:progress' % job_id, 0)
    r.set('job:%s:status' % job_id, 'running')
    threading.Thread(target=target, args=(job_id, request), daemon=True).start()
    return {'job_id': job_id}


def get_job_status(r, job_id):
    """Return ``(status_str, payload)``."""
    status = r.get('job:%s:status' % job_id)
    if status is None:
        return None, {'error': 'unknown_job_id'}
    status = status.decode()
    return status, status


def read_result_from_redis(r, job_id):
    """Return the stored result for *job_id*."""
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
            'message': (error_msg.decode() if error_msg else 'unknown error'),
        }
    if status == 'done':
        data = r.get('job:%s:result' % job_id)
        if not data:
            return {'status': 'error', 'message': 'missing_result'}
        return {'status': 'done', 'result': json.loads(data)}
    return {'error': 'unknown_status', 'status': status}


def progress_stream(r, job_id, poll_interval=0.5):
    """Yield SSE progress events for *job_id*."""
    while True:
        raw_progress = r.get('job:%s:progress' % job_id)
        raw_found = r.get('job:%s:found' % job_id)
        raw_not_found = r.get('job:%s:not_found' % job_id)
        raw_total = r.get('job:%s:total' % job_id)

        progress = int(raw_progress) if raw_progress else 0
        found = int(raw_found) if raw_found else 0
        not_found = int(raw_not_found) if raw_not_found else 0
        total = int(raw_total) if raw_total else 0

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
            p = r.get('job:%s:error' % job_id)
            jp = json.dumps(ast.literal_eval(p.decode()))
            yield ('event: error\ndata: %s\n\n' % jp).encode('utf-8')
            break

        time.sleep(poll_interval)


def store_job_progress(r, job_id, count, found, not_found):
    """Store job progress counters in Redis."""
    r.set('job:%s:progress' % job_id, count)
    r.set('job:%s:found' % job_id, found)
    r.set('job:%s:not_found' % job_id, not_found)
    r.publish('job:%s:events' % job_id, 'progress:%d' % count)
    r.publish('job:%s:events' % job_id, 'found:%d' % found)
    r.publish('job:%s:events' % job_id, 'not_found:%d' % not_found)
