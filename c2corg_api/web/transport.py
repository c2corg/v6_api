"""Timetables of the public transport lines and stops shown on the map.

The map itself comes from static vector tiles (see transport_tiles/). A click on
a line or a stop asks these routes for its planned timetable (Navitia, kept for
a day) and for the waypoints, routes and outings that its stops lead to.
"""

import datetime
import logging
import os
from typing import Annotated

from fastapi import Query, Response

from c2corg_api import caching
from c2corg_api.caching import cache_transport, get_or_create
from c2corg_api.httpexceptions import HTTPNotFound
from c2corg_api.transport import navitia
from c2corg_api.transport.associations import get_linked_documents
from c2corg_api.web.answers import http_error
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response
from c2corg_api.web.params import Lang, finite

log = logging.getLogger(__name__)

# the planned timetable changes slowly: browsers may keep it for a while too
CACHE_CONTROL = 'public, max-age=3600'
# a timetable of a day can be asked for from yesterday to about a year ahead
MAX_DAYS_AHEAD = 400
DEFAULT_TIMETABLE_SECONDS = 86400
DEFAULT_REQUESTS_PER_DAY = 5000

Lon = Annotated[
    finite('lon'),
    Query(ge=-180, le=180, description='The longitude of the place (WGS 84).'),
]
Lat = Annotated[
    finite('lat'),
    Query(ge=-90, le=90, description='The latitude of the place (WGS 84).'),
]
# checked by the route (400, as the days of the avalanche bulletins): the
# window depends on today
Day = Annotated[
    str | None,
    Query(description='The day of the timetable (YYYY-MM-DD), today by default.'),
]
TitleLang = Annotated[
    Lang | None,
    Query(description='The language of the titles of the documents: fr by default.'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    navitia.budget = navitia.DailyBudget(
        navitia_requests_per_day(), counter=count_navitia_request
    )
    for path, endpoint in (
        ('/transport/stops/schedules', transport_stop_schedules),
        ('/transport/lines/schedules', transport_line_schedules),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['transport'],
        )


def _int_from_env(name, default, minimum):
    try:
        return max(minimum, int(os.getenv(name) or default))
    except ValueError:
        log.warning(f'Invalid {name}, using {default}')
        return default


def navitia_requests_per_day():
    """Return the cap of the requests sent to Navitia in a day (0: none)."""
    return _int_from_env(
        'TRANSPORT_MAX_NAVITIA_REQUESTS_PER_DAY', DEFAULT_REQUESTS_PER_DAY, 0
    )


def timetable_seconds():
    """Return how long a timetable is kept: a day, or TRANSPORT_CACHE_SECONDS."""
    return _int_from_env('TRANSPORT_CACHE_SECONDS', DEFAULT_TIMETABLE_SECONDS, 60)


def count_navitia_request(day):
    """Count the requests sent on a day, in Redis (shared by all the servers)."""
    client = cache_transport.backend.writer_client
    key = f'{caching.KEY_PREFIX}:transport:requests:{day}'
    used = client.incr(key)
    if used == 1:
        client.expire(key, 2 * 86400)
    return used


def cached(kind, key, creator):
    """Return a value kept in Redis: the timetables for a day."""
    # the Navitia coverage of a place changes almost never: it is kept as long
    # as Redis keeps it (redis.expiration_time)
    expiration = -1 if kind == 'region' else timetable_seconds()
    return get_or_create(
        cache_transport, f'{kind}:{key}', creator, expiration_time=expiration
    )


def transport_stop_schedules(
    response: Response,
    lon: Lon,
    lat: Lat,
    date: Day = None,
    navitia_id: Annotated[
        str | None,
        Query(description='The Navitia id of the stop area, when the map knows it.'),
    ] = None,
    name: Annotated[
        str | None,
        Query(description='The name of the stop, to find it among those nearby.'),
    ] = None,
    lang: TitleLang = None,
):
    """Return the departures of a stop on a day, and what the stop leads to.

    The lines of the stop with their departures, the trips that run on demand,
    the next day of service when nothing runs, and the waypoints, routes and
    outings near the stop.
    """
    day = _day(date)
    if not isinstance(day, datetime.date):
        return day
    try:
        timetable = navitia.stop_timetable(
            lon, lat, day, cached, navitia_id=navitia_id or None, name=name or None
        )
    except navitia.NavitiaError as error:
        return _navitia_error(error)
    if timetable is None:
        return http_error(HTTPNotFound('unknown_stop'))
    with request_session() as session:
        associations = get_linked_documents(
            session, [timetable['stop_area']['id']], lang or 'fr'
        )
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {**timetable, 'associations': associations}


def transport_line_schedules(
    response: Response,
    lon: Lon,
    lat: Lat,
    ref: Annotated[
        str, Query(min_length=1, description='The number of the line, as in OSM.')
    ],
    network: Annotated[
        str | None, Query(description='The network of the line, as in OSM.')
    ] = None,
    date: Day = None,
    lang: TitleLang = None,
):
    """Return the timetable of a line on a day, and what its stops lead to.

    The line is found among the stops near the place clicked: one table per
    direction, with its stops and trips, and the waypoints, routes and outings
    near the stops of the line.
    """
    day = _day(date)
    if not isinstance(day, datetime.date):
        return day
    try:
        timetable = navitia.line_timetable(lon, lat, ref, network, day, cached)
    except navitia.NavitiaError as error:
        return _navitia_error(error)
    if timetable is None:
        return http_error(HTTPNotFound('unknown_line'))
    with request_session() as session:
        associations = get_linked_documents(
            session, timetable['stop_area_ids'], lang or 'fr'
        )
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {**timetable, 'associations': associations}


def _day(value):
    """Return the day asked for, or the answer to an invalid one."""
    today = navitia.paris_today()
    if not value:
        return today
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError:
        day = None
    # YYYY-MM-DD only: fromisoformat takes 20261122 and 2026-W47 too
    if day is None or len(value) != 10:
        return error_response([('querystring', 'date', 'invalid date (YYYY-MM-DD)')])
    if not (
        today - datetime.timedelta(days=1)
        <= day
        <= today + datetime.timedelta(days=MAX_DAYS_AHEAD)
    ):
        return error_response([('querystring', 'date', 'date out of range')])
    return day


def _navitia_error(error):
    """Answer a failure of Navitia with its status and its short code."""
    return error_response([('body', 'navitia', error.code)], error.status)


for endpoint in (transport_stop_schedules, transport_line_schedules):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
