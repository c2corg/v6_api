"""The stop areas of public transports, and the documents they make reachable."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.route import ReachableRouteRest
from c2corg_api.views.stoparea import StopareaInfoRest, StopareaRest
from c2corg_api.views.waypoint import ReachableWaypointRest
from c2corg_api.views.waypoint_stoparea import (
    WaypointStopareaInfoRest,
    WaypointStopareasByWaypointRest,
    WaypointStopareasReachableRest,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view, typed_values
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
    view = StopareaRest
    return serve_view(request, user, [typed_values(validated)], view, 'collection_get')


def stoparea(
    request: Request,
    user: User,
    id: DocumentId,
    lang: Annotated[Lang | None, Query(alias='l', description=UNUSED)] = None,
):
    """Return a stop area."""
    validated = {'id': id, 'lang': lang}
    return serve_view(request, user, [typed_values(validated)], StopareaRest)


def stoparea_info(request: Request, user: User, id: DocumentId, lang: PathLang):
    """Return the attributes of a stop area."""
    validated = {'id': id, 'lang': lang}
    return serve_view(request, user, [typed_values(validated)], StopareaInfoRest)


def _waypoint(waypoint_id):
    # the views read it in the path parameters, as an integer
    def validator(request, **kwargs):
        request.matchdict['waypoint_id'] = waypoint_id

    return validator


def waypoint_stopareas(request: Request, user: User, waypoint_id: WaypointId):
    """Return the stop areas near a waypoint, with their distance."""
    view = WaypointStopareasByWaypointRest
    return serve_view(request, user, [_waypoint(waypoint_id)], view)


def waypoint_is_reachable(request: Request, user: User, waypoint_id: WaypointId):
    """Return whether a waypoint has a stop area near it."""
    view = WaypointStopareasReachableRest
    return serve_view(request, user, [_waypoint(waypoint_id)], view)


def waypoint_stoparea_info(
    request: Request, user: User, id: DocumentId, lang: PathLang
):
    """Return the link between a waypoint and a stop area."""
    validated = {'id': id, 'lang': lang}
    view = WaypointStopareaInfoRest
    return serve_view(request, user, [typed_values(validated)], view)


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
    return serve_view(request, user, [typed_values(validated)], ReachableRouteRest)


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
    return serve_view(request, user, [typed_values(validated)], ReachableWaypointRest)


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
