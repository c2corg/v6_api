"""The Navitia routes: journeys, isochrones, and the jobs of the journey searches."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.navitia import (
    NavitiaIsochronesReachableRoutesRest,
    NavitiaIsochronesReachableWaypointsRest,
    NavitiaJourneyReachableRoutesProgressRest,
    NavitiaJourneyReachableRoutesResultRest,
    NavitiaJourneyReachableWaypointsProgressRest,
    NavitiaJourneyReachableWaypointsResultRest,
    NavitiaRest,
    StartNavitiaJourneyReachableRoutesRest,
    StartNavitiaJourneyReachableWaypointsRest,
    validate_isochrone_reachable_params,
    validate_journey_reachable_params,
    validate_navitia_params,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]

# (path, view class, validators)
ROUTES = [
    ('/navitia/journeys', NavitiaRest, [validate_navitia_params]),
    (
        '/navitia/isochronesreachableroutes',
        NavitiaIsochronesReachableRoutesRest,
        [validate_isochrone_reachable_params],
    ),
    (
        '/navitia/isochronesreachablewaypoints',
        NavitiaIsochronesReachableWaypointsRest,
        [validate_isochrone_reachable_params],
    ),
    (
        '/navitia/journeyreachableroutes/start',
        StartNavitiaJourneyReachableRoutesRest,
        [validate_journey_reachable_params],
    ),
    (
        '/navitia/journeyreachablewaypoints/start',
        StartNavitiaJourneyReachableWaypointsRest,
        [validate_journey_reachable_params],
    ),
    (
        '/navitia/journeyreachableroutes/result/{job_id}',
        NavitiaJourneyReachableRoutesResultRest,
        [],
    ),
    (
        '/navitia/journeyreachablewaypoints/result/{job_id}',
        NavitiaJourneyReachableWaypointsResultRest,
        [],
    ),
    # the progress is a stream of server-sent events, until the job ends
    (
        '/navitia/journeyreachableroutes/progress/{job_id}',
        NavitiaJourneyReachableRoutesProgressRest,
        [],
    ),
    (
        '/navitia/journeyreachablewaypoints/progress/{job_id}',
        NavitiaJourneyReachableWaypointsProgressRest,
        [],
    ),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, view_class, validators in ROUTES:
        app.add_api_route(
            path, _endpoint(view_class, validators), methods=['GET', 'HEAD']
        )


def _endpoint(view_class, validators):
    def endpoint(request: Request, user: User):
        return serve_view(request, user, validators, view_class)

    endpoint.__name__ = view_class.__name__
    return endpoint
