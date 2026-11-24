"""The outings of the partner sites, merged with those of c2c."""
# The parameters are read as strings and checked together by
# views.partner_outings (the date window and the rating interval are checked
# as a whole): an invalid one is a 400 `invalid <name>` in the error envelope.

from typing import Annotated

from fastapi import Query, Response

from c2corg_api.views.partner_outings import (
    DEFAULT_DAYS,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_SPAN_DAYS,
    InvalidParam,
    list_partner_outings,
    list_sources,
    parse_params,
)
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response

CACHE_CONTROL = 'public, max-age=120'

Text = str | None


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, endpoint in (
        ('/partner-outings', partner_outings),
        ('/partner-outings/sources', partner_outings_sources),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['partner-outings'],
        )


def partner_outings(
    response: Response,
    a: Annotated[Text, Query(description='Area ids, comma separated.')] = None,
    bbox: Annotated[
        Text, Query(description='`xmin,ymin,xmax,ymax` in EPSG:3857.')
    ] = None,
    date: Annotated[
        Text,
        Query(
            description='`YYYY-MM-DD` or `start,end` (at most '
            f'{MAX_SPAN_DAYS} days apart): the last {DEFAULT_DAYS} days by default.'
        ),
    ] = None,
    act: Annotated[Text, Query(description='Activities, comma separated.')] = None,
    trat: Annotated[
        Text,
        Query(description='Ski rating interval `min,max` (`3.1,4.3`, `,3.3`, `4.1,`).'),
    ] = None,
    steep: Annotated[
        Text, Query(description='`true`/`1` or `false`/`0`: steep skiing or not.')
    ] = None,
    sources: Annotated[
        Text,
        Query(description='Sources, comma separated, `c2c` included: all by default.'),
    ] = None,
    pl: Annotated[
        Text,
        Query(description='The language of the titles of c2c and of the areas.'),
    ] = None,
    limit: Annotated[
        Text, Query(description=f'1 to {MAX_LIMIT}: {DEFAULT_LIMIT} by default.')
    ] = None,
    offset: Annotated[Text, Query(description='The first result, from 0.')] = None,
):
    """Return the outings of the partner sites and of c2c, newest first.

    The answer is cached twice, in Redis (120 s) and by the clients
    (`Cache-Control: max-age=120`): a new harvest can take up to about 4
    minutes to show.
    """
    raw = {
        'a': a,
        'bbox': bbox,
        'date': date,
        'act': act,
        'trat': trat,
        'steep': steep,
        'sources': sources,
        'pl': pl,
        'limit': limit,
        'offset': offset,
    }
    try:
        params = parse_params(raw)
    except InvalidParam as e:
        return _invalid(e.name)
    with request_session() as session:
        answer = list_partner_outings(session, params)
    response.headers['Cache-Control'] = CACHE_CONTROL
    return answer


def partner_outings_sources():
    """Return the health of the partner sources."""
    with request_session() as session:
        return list_sources(session)


def _invalid(name):
    return error_response([('querystring', name, f'invalid {name}')], 400)


partner_outings.described = True
partner_outings.response_schema = 'PartnerOutings'
partner_outings_sources.described = True
partner_outings_sources.response_schema = 'PartnerSources'
