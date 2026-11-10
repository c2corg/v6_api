"""The routes an outing's GPS track most likely followed."""
# A GET with the track in the URL, as an encoded polyline: a POST would count
# in the write quota of the user (security.rate_limiting). The editor
# simplifies the track first, which keeps the URL to a few KB.

import math
from typing import Annotated

from fastapi import Depends, Query, Request
from pydantic import AfterValidator, WithJsonSchema
from pydantic_core import PydanticCustomError

from c2corg_api.models.common.attributes import activities
from c2corg_api.views.route_suggestion import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    decode_polyline,
    suggest_routes,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.handlers import serve_read, typed_values
from c2corg_api.web.params import Lang, Limit

User = Annotated[CurrentUser | None, Depends(current_user)]

# more points would not fit in a URL anyway
MAX_POINTS = 5000


def _track(value):
    try:
        points = decode_polyline(value)
    except TypeError, ValueError:
        points = []
    if not 2 <= len(points) <= MAX_POINTS or not all(
        math.isfinite(lon) and -180 <= lon <= 180 and -85 <= lat <= 85
        for lon, lat in points
    ):
        raise PydanticCustomError('c2corg', 'invalid track')
    return points


def _activities(value):
    values = [a for a in value.split(',') if a]
    if not values or any(a not in activities for a in values):
        raise PydanticCustomError('c2corg', 'invalid act')
    return values


# a string for FastAPI, a list once checked
Track = Annotated[
    str,
    AfterValidator(_track),
    WithJsonSchema({'type': 'string', 'format': 'encoded-polyline'}),
]
Activities = Annotated[
    str,
    AfterValidator(_activities),
    WithJsonSchema({'type': 'string'}),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    app.add_api_route(
        '/routes/suggest',
        suggested_routes,
        methods=['GET', 'HEAD'],
        operation_id=suggested_routes.__name__,
        tags=['routes'],
    )


def suggested_routes(
    request: Request,
    user: User,
    track: Annotated[
        Track,
        Query(
            description='The GPS track: an encoded polyline (precision 5) of '
            'WGS 84 points, as ol/format/Polyline writes them.'
        ),
    ],
    act: Annotated[
        Activities | None,
        Query(
            description='Only the routes of one of these activities, comma separated.'
        ),
    ] = None,
    limit: Annotated[
        Limit | None,
        Query(
            description=f'How many routes: {LIMIT_DEFAULT} by default, '
            f'{LIMIT_MAX} at most.'
        ),
    ] = None,
    lang: Annotated[
        Lang | None,
        Query(
            alias='pl',
            description='The preferred language: the locale of each route in this '
            'language if it exists, else in the best other one.',
        ),
    ] = None,
):
    """Return the routes the track most likely followed, best first."""
    # route tracks, waypoints and outings near the track decide the order
    validated = {'track': track, 'activities': act, 'limit': limit, 'lang': lang}
    return serve_read(request, user, [typed_values(validated)], suggest_routes)


# described in the OpenAPI document (see web.openapi), as a listing
suggested_routes.described = True
suggested_routes.response_schema = 'Documents'
