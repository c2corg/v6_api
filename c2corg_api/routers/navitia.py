"""
FastAPI Navitia router.

Provides:
  - ``/v2/navitia/journeys``
  - ``/v2/navitia/journeyreachableroutes/start``
  - ``/v2/navitia/journeyreachablewaypoints/start``
  - ``/v2/navitia/journeyreachableroutes/result/{job_id}``
  - ``/v2/navitia/journeyreachablewaypoints/result/{job_id}``
  - ``/v2/navitia/journeyreachableroutes/progress/{job_id}``
  - ``/v2/navitia/journeyreachablewaypoints/progress/{job_id}``
  - ``/v2/navitia/isochronesreachableroutes``
  - ``/v2/navitia/isochronesreachablewaypoints``

Mirrors ``c2corg_api.views.navitia``.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from shapely.geometry import shape
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.routers.helpers.linked_attributes import (
    build_reachable_route_query_with_waypoints,
    build_reachable_waypoints_query,
)
from c2corg_api.routers.helpers.navitia import (
    BASE_URL,
    collect_areas_from_results,
    collect_waypoints_from_results,
    extract_isochrone_params,
    extract_meta_params,
    get_navitia_isochrone,
    is_wp_in_isochrone,
    navitia_get,
    progress_stream,
    read_result_from_redis,
    redis_client,
    start_job_background,
)
from c2corg_api.schemas.listing import AreaListingSchema
from c2corg_api.schemas.route import RouteReadSchema
from c2corg_api.schemas.waypoint import WaypointReadSchema

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/navitia', tags=['navitia'])


def _dump(schema_cls, obj):
    """Validate an SA object with a Pydantic schema and return a dict."""
    return schema_cls.model_validate(obj).model_dump(exclude_none=True)


# ──────────────────────────────────────────────────────────────
# GET /v2/navitia/journeys
# ──────────────────────────────────────────────────────────────

JOURNEY_REQUIRED = ['from', 'to', 'datetime', 'datetime_represents']
JOURNEY_OPTIONAL = [
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


@router.get('/journeys')
def get_journeys(request: Request, db: Session = Depends(get_db)):
    """Proxy to Navitia Journey API."""
    import os

    # Validate required params
    for param in JOURNEY_REQUIRED:
        if param not in request.query_params:
            raise HTTPException(
                status_code=400,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'location': 'querystring',
                            'name': param,
                            'description': 'Parameter %s required' % param,
                        }
                    ],
                },
            )

    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail='Navitia API config is missing')

    params = {
        'from': request.query_params.get('from'),
        'to': request.query_params.get('to'),
        'datetime': request.query_params.get('datetime'),
        'datetime_represents': request.query_params.get('datetime_represents'),
    }

    for param in JOURNEY_OPTIONAL:
        if param in request.query_params:
            params[param] = request.query_params.get(param)

    return navitia_get(
        BASE_URL + '/journeys', params=params, headers={'Authorization': api_key}
    )


# ──────────────────────────────────────────────────────────────
# Reachable routes / waypoints — background jobs
# ──────────────────────────────────────────────────────────────

REACHABLE_REQUIRED = [
    'from',
    'datetime',
    'datetime_represents',
    'walking_speed',
    'max_walking_duration_to_pt',
]


def _validate_reachable_params(request: Request):
    for param in REACHABLE_REQUIRED:
        if param not in request.query_params:
            raise HTTPException(
                status_code=400,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'location': 'querystring',
                            'name': param,
                            'description': 'Parameter %s required' % param,
                        }
                    ],
                },
            )


class _FakeValidated(dict):
    """Minimal stand-in that allows ``request.validated['lang']``
    to work in ``extract_meta_params``."""

    pass


class _RequestAdapter:
    """Adapt a FastAPI ``Request`` to the subset of the Pyramid request
    interface used by the background compute functions."""

    def __init__(self, starlette_request: Request):
        self._request = starlette_request
        self.params = dict(starlette_request.query_params)
        self.GET = dict(starlette_request.query_params)
        self.validated = _FakeValidated(lang=self.params.get('pl'))


@router.get('/journeyreachableroutes/start')
def start_journey_reachable_routes(request: Request, db: Session = Depends(get_db)):
    """Start background job for journey reachable routes."""
    _validate_reachable_params(request)
    from c2corg_api.routers.helpers.navitia_jobs import compute_journey_reachable_routes

    adapter = _RequestAdapter(request)
    return start_job_background(compute_journey_reachable_routes, adapter)


@router.get('/journeyreachablewaypoints/start')
def start_journey_reachable_waypoints(request: Request, db: Session = Depends(get_db)):
    """Start background job for journey reachable waypoints."""
    _validate_reachable_params(request)
    from c2corg_api.routers.helpers.navitia_jobs import (
        compute_journey_reachable_waypoints,
    )

    adapter = _RequestAdapter(request)
    return start_job_background(compute_journey_reachable_waypoints, adapter)


# ── result endpoints ─────────────────────────────────────────


@router.get('/journeyreachableroutes/result/{job_id}')
def get_journey_reachable_routes_result(job_id: str):
    """Return the result of a journey reachable routes job."""
    r = redis_client()
    return read_result_from_redis(r, job_id)


@router.get('/journeyreachablewaypoints/result/{job_id}')
def get_journey_reachable_waypoints_result(job_id: str):
    """Return the result of a journey reachable waypoints job."""
    r = redis_client()
    return read_result_from_redis(r, job_id)


# ── progress (SSE) endpoints ────────────────────────────────


@router.get('/journeyreachableroutes/progress/{job_id}')
def get_journey_reachable_routes_progress(job_id: str):
    """Stream progress of a journey reachable routes job via SSE."""
    r = redis_client()
    return StreamingResponse(progress_stream(r, job_id), media_type='text/event-stream')


@router.get('/journeyreachablewaypoints/progress/{job_id}')
def get_journey_reachable_waypoints_progress(job_id: str):
    """Stream progress of a journey reachable waypoints job via SSE."""
    r = redis_client()
    return StreamingResponse(progress_stream(r, job_id), media_type='text/event-stream')


# ──────────────────────────────────────────────────────────────
# Isochrone reachable routes / waypoints
# ──────────────────────────────────────────────────────────────

ISOCHRONE_REQUIRED = ['from', 'datetime', 'datetime_represents', 'boundary_duration']


def _validate_isochrone_params(request: Request):
    for param in ISOCHRONE_REQUIRED:
        if param not in request.query_params:
            raise HTTPException(
                status_code=400,
                detail={
                    'status': 'error',
                    'errors': [
                        {
                            'location': 'querystring',
                            'name': param,
                            'description': 'Parameter %s required' % param,
                        }
                    ],
                },
            )


@router.get('/isochronesreachableroutes')
def get_isochrones_reachable_routes(request: Request, db: Session = Depends(get_db)):
    """Return routes reachable within the Navitia isochrone."""
    _validate_isochrone_params(request)
    adapter = _RequestAdapter(request)

    try:
        meta_params = extract_meta_params(adapter)
        isochrone_params = extract_isochrone_params(adapter)

        query, _ = build_reachable_route_query_with_waypoints(adapter.GET, meta_params)

        if query is None:
            results = []
        else:
            results = query.all()

        areas_map = collect_areas_from_results(results, 1)

        response = get_navitia_isochrone(isochrone_params)

        routes = []
        geojson = ''
        if len(response['isochrones']) > 0:
            geojson = response['isochrones'][0]['geojson']
            isochrone_geom = shape(geojson)

            wp_objects = collect_waypoints_from_results(results)

            navitia_wp_map = {
                wp.document_id: is_wp_in_isochrone(
                    _dump(WaypointReadSchema, wp), isochrone_geom
                )
                for wp in wp_objects
            }

            for route, areas, waypoints in results:
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
                            json_areas.append(_dump(AreaListingSchema, area_obj))
                    route.areas = json_areas
                    routes.append(_dump(RouteReadSchema, route))

        return {'documents': routes, 'total': len(routes), 'isochron_geom': geojson}
    except Exception as e:
        return json.dumps(str(e))


@router.get('/isochronesreachablewaypoints')
def get_isochrones_reachable_waypoints(request: Request, db: Session = Depends(get_db)):
    """Return waypoints reachable within the Navitia isochrone."""
    _validate_isochrone_params(request)
    adapter = _RequestAdapter(request)

    try:
        meta_params = extract_meta_params(adapter)
        isochrone_params = extract_isochrone_params(adapter)

        query, _ = build_reachable_waypoints_query(adapter.GET, meta_params)
        results = query.all()

        areas_map = collect_areas_from_results(results, 1)

        response = get_navitia_isochrone(isochrone_params)

        waypoints = []
        geojson = ''
        if len(response['isochrones']) > 0:
            geojson = response['isochrones'][0]['geojson']
            isochrone_geom = shape(geojson)

            for waypoint, areas in results:
                if is_wp_in_isochrone(
                    _dump(WaypointReadSchema, waypoint), isochrone_geom
                ):
                    json_areas = []
                    if areas is None:
                        areas = []
                    for area in areas:
                        area_obj = areas_map.get(area.get('document_id'))
                        if area_obj:
                            json_areas.append(_dump(AreaListingSchema, area_obj))
                    waypoint.areas = json_areas
                    waypoints.append(_dump(WaypointReadSchema, waypoint))

        return {
            'documents': waypoints,
            'total': len(waypoints),
            'isochron_geom': geojson,
        }
    except Exception as e:
        return json.dumps(str(e))
