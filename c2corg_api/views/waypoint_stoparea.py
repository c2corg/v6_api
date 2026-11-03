from sqlalchemy import exists, func

from c2corg_api.models import DBSession
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.views.document import make_validator_create, make_validator_update
from c2corg_api.views.resource import view
from c2corg_api.views.validation import validate_id, validate_lang

validate_waypoint_stoparea_create = make_validator_create(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id'
)
validate_waypoint_stoparea_update = make_validator_update(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id'
)


@view(validators=[validate_id, validate_lang])
def get_waypoint_stoparea_info(request):
    waypoint_stoparea_id = request.matchdict['id']
    waypoint_stoparea = (
        DBSession.query(WaypointStoparea)
        .filter_by(waypoint_stoparea_id=waypoint_stoparea_id)
        .first()
    )

    if not waypoint_stoparea:
        request.response.status = 404
        return {'error': 'Waypoint Stoparea not found'}

    return {
        'waypoint_stoparea_id': waypoint_stoparea.waypoint_stoparea_id,
        'attributes': {
            'stoparea_id': waypoint_stoparea.stoparea_id,
            'waypoint_id': waypoint_stoparea.waypoint_id,
            'distance': waypoint_stoparea.distance,
        },
    }


get_waypoint_stoparea_info.view_name = 'WaypointStopareaInfoRest.get'


def validate_waypoint_id(request, *args, **kwargs):
    """Check that the waypoint id is a number, as the other id validators."""
    try:
        request.matchdict['waypoint_id'] = int(request.matchdict['waypoint_id'])
    except KeyError, ValueError:
        request.errors.add('querystring', 'waypoint_id', 'invalid waypoint_id')


@view(validators=[validate_waypoint_id])
def read_waypoint_stopareas(request):
    """Return the stopareas of a waypoint with their distance.

    Returns all stopareas associated with a waypoint,
    with their full attributes and distance.
    """
    waypoint_id = request.matchdict['waypoint_id']

    query = (
        DBSession.query(
            Stoparea,
            WaypointStoparea.distance,
            func.ST_X(Stoparea.geom).label('x'),
            func.ST_Y(Stoparea.geom).label('y'),
        )
        .join(WaypointStoparea, Stoparea.stoparea_id == WaypointStoparea.stoparea_id)
        .filter(WaypointStoparea.waypoint_id == waypoint_id)
        .all()
    )

    stopareas_data = [
        {**stoparea.to_dict(), 'distance': round(distance, 2)}
        for stoparea, distance, x, y in query
    ]

    return {'waypoint_id': waypoint_id, 'stopareas': stopareas_data}


read_waypoint_stopareas.view_name = 'WaypointStopareasByWaypointRest.get'


@view(validators=[validate_waypoint_id])
def read_waypoint_reachability(request):
    """Return whether the waypoint has at least one stoparea.

    Returns true if the waypoint has at least one stoparea
    associated with it, false otherwise.
    """
    waypoint_id = request.matchdict['waypoint_id']

    has_stopareas = DBSession.query(
        exists().where(WaypointStoparea.waypoint_id == waypoint_id)
    ).scalar()

    return has_stopareas


read_waypoint_reachability.view_name = 'WaypointStopareasReachableRest.get'
