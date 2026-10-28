"""The stop areas of public transports, and those near a waypoint."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.stoparea import (
    StopareaInfoRest,
    StopareaRest,
    validate_page_params,
)
from c2corg_api.views.validation import (
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)
from c2corg_api.views.waypoint_stoparea import (
    WaypointStopareaInfoRest,
    WaypointStopareasByWaypointRest,
    WaypointStopareasReachableRest,
    validate_waypoint_id,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    app.add_api_route('/stopareas', stoparea_listing, methods=methods)
    app.add_api_route('/stopareas/{id:int}', stoparea, methods=methods)
    app.add_api_route('/stopareas/{id:int}/{lang}/info', stoparea_info, methods=methods)
    app.add_api_route(
        '/waypoints/{waypoint_id}/stopareas', waypoint_stopareas, methods=methods
    )
    app.add_api_route(
        '/waypoints/{waypoint_id}/isReachable', waypoint_is_reachable, methods=methods
    )
    app.add_api_route(
        '/waypoints_stopareas/{id:int}/{lang}/info',
        waypoint_stoparea_info,
        methods=methods,
    )


def stoparea_listing(request: Request, user: User):
    """Return a page of the stop areas."""
    validators = [
        validate_pagination,
        validate_preferred_lang_param,
        validate_page_params,
    ]
    return serve_view(request, user, validators, StopareaRest, 'collection_get')


def stoparea(request: Request, user: User):
    """Return a stop area."""
    validators = [validate_id, validate_lang_param]
    return serve_view(request, user, validators, StopareaRest)


def stoparea_info(request: Request, user: User):
    """Return the attributes of a stop area."""
    return serve_view(request, user, [validate_id, validate_lang], StopareaInfoRest)


def waypoint_stopareas(request: Request, user: User):
    """Return the stop areas near a waypoint, with their distance."""
    return serve_view(
        request, user, [validate_waypoint_id], WaypointStopareasByWaypointRest
    )


def waypoint_is_reachable(request: Request, user: User):
    """Return whether a waypoint has a stop area near it."""
    return serve_view(
        request, user, [validate_waypoint_id], WaypointStopareasReachableRest
    )


def waypoint_stoparea_info(request: Request, user: User):
    """Return the link between a waypoint and a stop area."""
    validators = [validate_id, validate_lang]
    return serve_view(request, user, validators, WaypointStopareaInfoRest)
