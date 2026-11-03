"""The Navitia routes: journeys, isochrones, and the jobs of the journey searches."""
# The routes call the functions of views/ through web.handlers, as the
# document routes do (#2365). Their parameters are
# declared (#2512): the required ones are checked for their presence only, as
# their validators did, and the views read them all in the query string.

from inspect import Parameter, Signature
from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.navitia import (
    read_isochrone_reachable_routes,
    read_isochrone_reachable_waypoints,
    read_journey_reachable_routes_progress,
    read_journey_reachable_routes_result,
    read_journey_reachable_waypoints_progress,
    read_journey_reachable_waypoints_result,
    read_journeys,
    start_journey_reachable_routes,
    start_journey_reachable_waypoints,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.handlers import serve_read

User = Annotated[CurrentUser | None, Depends(current_user)]

JOURNEY = ['from', 'to', 'datetime', 'datetime_represents']
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
ISOCHRONE = ['from', 'datetime', 'datetime_represents', 'boundary_duration']
JOURNEY_REACHABLE = [
    'from',
    'datetime',
    'datetime_represents',
    'walking_speed',
    'max_walking_duration_to_pt',
]

# (path, function, required parameters, optional parameters)
ROUTES = [
    ('/navitia/journeys', read_journeys, JOURNEY, JOURNEY_OPTIONAL),
    (
        '/navitia/isochronesreachableroutes',
        read_isochrone_reachable_routes,
        ISOCHRONE,
        [],
    ),
    (
        '/navitia/isochronesreachablewaypoints',
        read_isochrone_reachable_waypoints,
        ISOCHRONE,
        [],
    ),
    (
        '/navitia/journeyreachableroutes/start',
        start_journey_reachable_routes,
        JOURNEY_REACHABLE,
        [],
    ),
    (
        '/navitia/journeyreachablewaypoints/start',
        start_journey_reachable_waypoints,
        JOURNEY_REACHABLE,
        [],
    ),
    (
        '/navitia/journeyreachableroutes/result/{job_id}',
        read_journey_reachable_routes_result,
        [],
        [],
    ),
    (
        '/navitia/journeyreachablewaypoints/result/{job_id}',
        read_journey_reachable_waypoints_result,
        [],
        [],
    ),
    # the progress is a stream of server-sent events, until the job ends
    (
        '/navitia/journeyreachableroutes/progress/{job_id}',
        read_journey_reachable_routes_progress,
        [],
        [],
    ),
    (
        '/navitia/journeyreachablewaypoints/progress/{job_id}',
        read_journey_reachable_waypoints_progress,
        [],
        [],
    ),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, function, required, optional in ROUTES:
        app.add_api_route(
            path,
            _endpoint(function, required, optional, '{job_id}' in path),
            methods=['GET', 'HEAD'],
            operation_id=function.__name__,
            tags=['navitia'],
        )


def _endpoint(function, required, optional, job):
    def endpoint(request: Request, user: User, **parameters):
        return serve_read(request, user, [], function)

    endpoint.__name__ = function.__name__
    endpoint.__signature__ = Signature(
        [
            Parameter('request', Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
            Parameter('user', Parameter.POSITIONAL_OR_KEYWORD, annotation=User),
            *_parameters(required, optional, job),
        ]
    )
    # the message of the validators for a missing parameter
    endpoint.missing_message = 'Parameter {name} required'
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
    return endpoint


def _parameters(required, optional, job):
    # `from` is a Python keyword: the parameters are named by their alias
    if job:
        yield Parameter(
            'job_id',
            Parameter.KEYWORD_ONLY,
            annotation=Annotated[str, Path(description='The id of the job.')],
        )
    for name in required:
        query = Query(alias=name, description='Required, passed to Navitia.')
        yield Parameter(
            f'p_{name}', Parameter.KEYWORD_ONLY, annotation=Annotated[str, query]
        )
    for name in optional:
        query = Query(alias=name, description='Passed to Navitia.')
        yield Parameter(
            f'p_{name}',
            Parameter.KEYWORD_ONLY,
            annotation=Annotated[str | None, query],
            default=None,
        )
