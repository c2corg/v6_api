"""The avalanche bulletins of the EAWS regions, as CAAML v6 JSON."""
# The French massifs from Météo-France (c2corg/v6_api#2681), whose numbers are
# the EAWS region ids FR-01 to FR-74; the regions of the Alps and the Pyrenees
# whose services publish CAAML v6 (#2683). Harvested by the scheduler (#2682):
# the latest ones, those of a day (#2686), the day they are valid for as the
# EAWS services name their files, and the danger of each day.

import logging
import re
from datetime import date, timedelta
from typing import Annotated

from fastapi import Path, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from c2corg_api.avalanche_bulletins import meteofrance
from c2corg_api.avalanche_bulletins.cache import UpstreamError
from c2corg_api.avalanche_bulletins.regions import (
    UnknownRegion,
    day_bulletins,
    is_over,
    latest_bulletins,
    ratings,
    stored_latest,
)
from c2corg_api.httpexceptions import HTTPNotFound, HTTPServiceUnavailable
from c2corg_api.web.answers import http_error
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response
from c2corg_api.web.params import Lang

log = logging.getLogger(__name__)

RegionId = Annotated[
    str,
    Path(
        description='The EAWS region id: `FR-03` (a massif of Météo-France), '
        '`CH-4231`, `AT-07-14-01`... or a region holding others (`CH`).',
        pattern=r'^[A-Z]{2}(-[A-Z0-9]{1,6}){0,4}$',
    ),
]
BulletinLang = Annotated[
    Lang | None,
    Query(
        description='The language of the bulletin, if its service publishes it '
        '(else English). Météo-France publishes in French only.'
    ),
]

# checked by the view (400, as the dates of /ratings): a pattern would answer
# FastAPI's 422
Day = Annotated[
    str,
    Path(
        description='The day the bulletins are valid for (YYYY-MM-DD): the '
        'bulletin published the evening before, maybe updated the morning.',
    ),
]
DATE = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')

# the API cache follows the publications, the browsers keep a bulletin briefly
CACHE_CONTROL = 'public, max-age=300'
# the bulletins of a day over do not change anymore
CACHE_CONTROL_OVER = 'public, max-age=604800, immutable'

# the days of the danger by default, and at most
RATINGS_DAYS = 7
RATINGS_MAX_DAYS = 366


def include(app):
    """Add the routes of this module to the FastAPI application."""
    # the day last: `latest` and `ratings` are not days
    for path, endpoint in (
        ('/avalanche-bulletins/regions/{region_id}/latest', avalanche_bulletin),
        (
            '/avalanche-bulletins/regions/{region_id}/latest/pdf',
            avalanche_bulletin_pdf,
        ),
        (
            '/avalanche-bulletins/regions/{region_id}/ratings',
            avalanche_bulletin_ratings,
        ),
        ('/avalanche-bulletins/regions/{region_id}/{day}', avalanche_bulletin_day),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['avalanche-bulletins'],
        )


def avalanche_bulletin(
    region_id: RegionId, response: Response, lang: BulletinLang = None
):
    """Return the last bulletins published for a region, as CAAML v6."""
    # the session ended before a fetch: a slow service holds no connection
    with request_session() as session:
        bulletins = stored_latest(session, region_id, lang)
    try:
        if not bulletins:
            bulletins = latest_bulletins(region_id, lang)
    except UnknownRegion:
        return http_error(HTTPNotFound('no avalanche bulletin for this region'))
    except UpstreamError:
        return http_error(HTTPServiceUnavailable('the bulletin service did not answer'))
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {'bulletins': bulletins}


def avalanche_bulletin_pdf(region_id: RegionId):
    """Return the official PDF of the last bulletin of a French massif."""
    massif = meteofrance.massif_of(region_id)
    if massif is None:
        return http_error(HTTPNotFound('no PDF bulletin for this region'))
    try:
        content = meteofrance.pdf(massif)
    except UpstreamError:
        return http_error(HTTPServiceUnavailable('Météo-France did not answer'))
    if content is None:
        return http_error(HTTPNotFound('no avalanche bulletin for this region now'))
    return Response(
        content,
        media_type='application/pdf',
        headers={
            'Cache-Control': CACHE_CONTROL,
            'Content-Disposition': f'inline; filename="BRA-{region_id}.pdf"',
        },
    )


def avalanche_bulletin_day(
    region_id: RegionId, day: Day, response: Response, lang: BulletinLang = None
):
    """Return the bulletins of a region for a day, as CAAML v6."""
    day = _date(day)
    if day is None:
        return error_response([('path', 'day', 'invalid date (YYYY-MM-DD)')])
    try:
        with request_session() as session:
            bulletins = day_bulletins(session, region_id, day, lang)
    except SQLAlchemyError:
        return _not_stored(region_id)
    if not bulletins:
        return http_error(HTTPNotFound('no avalanche bulletin for this region and day'))
    response.headers['Cache-Control'] = (
        CACHE_CONTROL_OVER if is_over(day) else CACHE_CONTROL
    )
    return {'bulletins': bulletins}


def avalanche_bulletin_ratings(
    region_id: RegionId,
    response: Response,
    date_from: Annotated[
        str | None,
        Query(
            alias='from',
            description='The first day (YYYY-MM-DD), by default 6 days before `to`.',
        ),
    ] = None,
    date_to: Annotated[
        str | None,
        Query(alias='to', description='The last day (YYYY-MM-DD), by default today.'),
    ] = None,
):
    """Return the danger of a region and of its sub-regions, day by day.

    By day: the highest rating (1 low to 5 very high, null without) of the
    region and its sub-regions, and the danger of each (ratings below and
    above the elevation bound, all the bands, problems, aspects). The days
    without bulletin are left out; at most a year.
    """
    to = _date(date_to) if date_to else _today()
    if to is None:
        return error_response([('querystring', 'to', 'invalid date (YYYY-MM-DD)')])
    since = _date(date_from) if date_from else to - timedelta(days=RATINGS_DAYS - 1)
    if since is None:
        return error_response([('querystring', 'from', 'invalid date (YYYY-MM-DD)')])
    if since > to:
        return error_response([('querystring', 'from', 'after to')])
    if (to - since).days >= RATINGS_MAX_DAYS:
        return error_response(
            [('querystring', 'from', f'more than {RATINGS_MAX_DAYS} days')]
        )
    try:
        with request_session() as session:
            days = ratings(session, region_id, since, to)
    except SQLAlchemyError:
        return _not_stored(region_id)
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {'days': days}


def _not_stored(region_id):
    # the database fails, or its tables are not there yet (a deployment
    # before `alembic upgrade head`): the stored bulletins are unavailable
    log.exception('Reading the stored bulletins of %s failed', region_id)
    return http_error(HTTPServiceUnavailable('the stored bulletins are not available'))


def _date(value):
    # YYYY-MM-DD only: fromisoformat takes 20261122 and 2026-W47 too
    if not DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _today():
    from c2corg_api.avalanche_bulletins import regions

    return regions._now().date()


for endpoint in (
    avalanche_bulletin,
    avalanche_bulletin_pdf,
    avalanche_bulletin_day,
    avalanche_bulletin_ratings,
):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
