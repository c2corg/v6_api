"""
Background job functions for Navitia journey-reachable computations.

Extracted from ``c2corg_api.views.navitia`` so that the FastAPI router
can use them without importing from ``views/``.
"""

import json
import logging

from fastapi import HTTPException

from c2corg_api.routers.helpers.linked_attributes import (
    build_reachable_route_query_with_waypoints,
    build_reachable_waypoints_query,
)
from c2corg_api.routers.helpers.navitia import (
    MAX_ROUTE_THRESHOLD,
    collect_areas_from_results,
    collect_waypoints_from_results,
    extract_journey_params,
    extract_meta_params,
    is_wp_journey_reachable,
    redis_client,
    store_job_progress,
)
from c2corg_api.schemas.listing import AreaListingSchema
from c2corg_api.schemas.route import RouteReadSchema
from c2corg_api.schemas.waypoint import WaypointReadSchema

log = logging.getLogger(__name__)


def _dump(schema_cls, obj):
    """Validate an SA object with a Pydantic schema and return a dict."""
    return schema_cls.model_validate(obj).model_dump(exclude_none=True)


def compute_journey_reachable_routes(job_id, request):
    """Compute journey-reachable routes in a background thread."""
    r = redis_client()
    try:
        meta_params = extract_meta_params(request)
        journey_params = extract_journey_params(request)
        query, _count = build_reachable_route_query_with_waypoints(
            request.GET, meta_params
        )
        if query is None:
            results = []
        else:
            results = query.all()

        if len(results) > MAX_ROUTE_THRESHOLD:
            raise HTTPException(400, "Couldn't proceed: too many routes found.")

        areas_map = collect_areas_from_results(results, 1)
        wp_objects = collect_waypoints_from_results(results)

        total = len(wp_objects)
        log.info('Number of NAVITIA journey queries: %d', total)
        r.set('job:%s:total' % job_id, total)

        count = found = not_found = 0
        navitia_wp_map = {}

        for wp in wp_objects:
            result = is_wp_journey_reachable(
                _dump(WaypointReadSchema, wp), journey_params
            )
            navitia_wp_map[wp.document_id] = result
            count += 1
            if result:
                found += 1
            else:
                not_found += 1
            store_job_progress(r, job_id, count, found, not_found)

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
                    json_areas.append(_dump(AreaListingSchema, area_obj))
            route.areas = json_areas
            routes.append(_dump(RouteReadSchema, route))

        r.set(
            'job:%s:result' % job_id,
            json.dumps({'documents': routes, 'total': len(routes)}),
        )
        r.set('job:%s:status' % job_id, 'done')
    except Exception as exc:
        log.exception(str(exc))
        r.set('job:%s:status' % job_id, 'error')
        r.set('job:%s:error' % job_id, str(exc))


def compute_journey_reachable_waypoints(job_id, request):
    """Compute journey-reachable waypoints in a background thread."""
    r = redis_client()
    try:
        meta_params = extract_meta_params(request)
        journey_params = extract_journey_params(request)

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
            raise HTTPException(400, 'Missing filter: area is required')
        if len(areas_list) > 1:
            raise HTTPException(400, 'Only one filtering area is allowed')

        query, _count = build_reachable_waypoints_query(request.GET, meta_params)
        results = query.all()

        areas_map = collect_areas_from_results(results, 1)

        total = len(results)
        log.info('Number of NAVITIA journey queries: %d', total)
        r.set('job:%s:total' % job_id, total)

        count = found = not_found = 0
        waypoints = []

        for waypoint, areas in results:
            count += 1
            r.publish('job:%s:events' % job_id, 'not_found:%d' % not_found)
            reachable = is_wp_journey_reachable(
                _dump(WaypointReadSchema, waypoint), journey_params
            )
            if reachable:
                found += 1
                json_areas = []
                for area in areas or []:
                    area_obj = areas_map.get(area.get('document_id'))
                    if area_obj:
                        json_areas.append(_dump(AreaListingSchema, area_obj))
                waypoint.areas = json_areas
                waypoints.append(_dump(WaypointReadSchema, waypoint))
            else:
                not_found += 1
            store_job_progress(r, job_id, count, found, not_found)

        r.set(
            'job:%s:result' % job_id,
            json.dumps({'documents': waypoints, 'total': len(waypoints)}),
        )
        r.set('job:%s:status' % job_id, 'done')
    except Exception as exc:
        log.exception('Error computing reachable waypoints')
        r.set('job:%s:status' % job_id, 'error')
        r.set('job:%s:error' % job_id, str(exc))
