"""The stop areas of public transports, and the documents they make reachable."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.route import list_reachable_routes
from c2corg_api.views.stoparea import (
    list_stopareas,
    read_stoparea,
    read_stoparea_info,
)
from c2corg_api.views.waypoint import list_reachable_waypoints
from c2corg_api.views.waypoint_stoparea import (
    get_waypoint_stoparea_info,
    read_waypoint_reachability,
    read_waypoint_stopareas,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_read, typed_values
from c2corg_api.web.params import (
    DocumentId,
    Lang,
    Limit,
    Offset,
    PathLang,
    integer,
    positive,
)

User = Annotated[CurrentUser | None, Depends(current_user)]
PageOffset = Annotated[Offset | None, Query(description='The first result, from 0.')]
PageLimit = Annotated[
    Limit | None, Query(description='How many results: 30 by default.')
]
PreferredLang = Annotated[
    Lang | None,
    Query(
        alias='pl',
        description='The locale of each document in this language if it exists, '
        'else in the best other one.',
    ),
]
UNUSED = 'Checked, not used.'
WaypointId = Annotated[integer('waypoint_id'), Path(description='The waypoint id.')]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    for path, endpoint, tag in (
        ('/stopareas', stoparea_listing, 'stopareas'),
        ('/stopareas/{id:int}', stoparea, 'stopareas'),
        ('/stopareas/{id:int}/{lang}/info', stoparea_info, 'stopareas'),
        ('/waypoints/{waypoint_id}/stopareas', waypoint_stopareas, 'waypoints'),
        ('/waypoints/{waypoint_id}/isReachable', waypoint_is_reachable, 'waypoints'),
        (
            '/waypoints_stopareas/{id:int}/{lang}/info',
            waypoint_stoparea_info,
            'stopareas',
        ),
        ('/reachableroutes', reachable_routes, 'routes'),
        ('/reachablewaypoints', reachable_waypoints, 'waypoints'),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=endpoint.__name__,
            tags=[tag],
        )


def stoparea_listing(
    request: Request,
    user: User,
    # checked as the other listings do, but not used: the stop areas are paged
    # with page_id and nb_items
    offset: Annotated[Offset | None, Query(description=UNUSED)] = None,
    limit: Annotated[Limit | None, Query(description=UNUSED)] = None,
    lang: Annotated[Lang | None, Query(alias='pl', description=UNUSED)] = None,
    page_id: Annotated[
        positive('page_id') | None, Query(description='The page, from 1.')
    ] = None,
    nb_items: Annotated[
        positive('nb_items') | None,
        Query(description='The stop areas per page: 30 by default.'),
    ] = None,
):
    """Return a page of the stop areas."""
    validated = {
        'offset': offset,
        'limit': limit,
        'lang': lang,
        'page_id': page_id,
        'nb_items': nb_items,
    }
    return serve_read(request, user, [typed_values(validated)], list_stopareas)


def stoparea(
    request: Request,
    user: User,
    id: DocumentId,
    lang: Annotated[Lang | None, Query(alias='l', description=UNUSED)] = None,
):
    """Return a stop area."""
    validated = {'id': id, 'lang': lang}
    return serve_read(request, user, [typed_values(validated)], read_stoparea)


def stoparea_info(request: Request, user: User, id: DocumentId, lang: PathLang):
    """Return the attributes of a stop area."""
    validated = {'id': id, 'lang': lang}
    return serve_read(request, user, [typed_values(validated)], read_stoparea_info)


def _waypoint(waypoint_id):
    # the views read it in the path parameters, as an integer
    def validator(request, **kwargs):
        request.matchdict['waypoint_id'] = waypoint_id

    return validator


def waypoint_stopareas(request: Request, user: User, waypoint_id: WaypointId):
    """Return the stop areas near a waypoint, with their distance."""
    return serve_read(request, user, [_waypoint(waypoint_id)], read_waypoint_stopareas)


def waypoint_is_reachable(request: Request, user: User, waypoint_id: WaypointId):
    """Return whether a waypoint has a stop area near it."""
    return serve_read(
        request, user, [_waypoint(waypoint_id)], read_waypoint_reachability
    )


def waypoint_stoparea_info(
    request: Request, user: User, id: DocumentId, lang: PathLang
):
    """Return the link between a waypoint and a stop area."""
    validated = {'id': id, 'lang': lang}
    return serve_read(
        request, user, [typed_values(validated)], get_waypoint_stoparea_info
    )


def reachable_routes(
    request: Request,
    user: User,
    offset: PageOffset = None,
    limit: PageLimit = None,
    lang: PreferredLang = None,
):
    """Return the routes with an access waypoint near a stop area."""
    # the search filters of the routes are read by the view
    validated = {'offset': offset, 'limit': limit, 'lang': lang}
    return serve_read(request, user, [typed_values(validated)], list_reachable_routes)


def reachable_waypoints(
    request: Request,
    user: User,
    offset: PageOffset = None,
    limit: PageLimit = None,
    lang: PreferredLang = None,
):
    """Return the access waypoints near a stop area."""
    # the search filters of the waypoints are read by the view
    validated = {'offset': offset, 'limit': limit, 'lang': lang}
    return serve_read(
        request, user, [typed_values(validated)], list_reachable_waypoints
    )


for endpoint in (
    stoparea_listing,
    stoparea,
    stoparea_info,
    waypoint_stopareas,
    waypoint_is_reachable,
    waypoint_stoparea_info,
    reachable_routes,
    reachable_waypoints,
):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
