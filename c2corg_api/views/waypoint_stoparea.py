from sqlalchemy import exists, func

from c2corg_api.models import DBSession
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.views.document import make_validator_create, make_validator_update
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.resource import resource, view
from c2corg_api.views.validation import validate_id, validate_lang

validate_waypoint_stoparea_create = make_validator_create(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id'
)
validate_waypoint_stoparea_update = make_validator_update(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id'
)


@resource(path='/waypoints_stopareas/{id}/{lang}/info')
class WaypointStopareaInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        waypoint_stoparea_id = self.request.matchdict['id']
        waypoint_stoparea = (
            DBSession.query(WaypointStoparea)
            .filter_by(waypoint_stoparea_id=waypoint_stoparea_id)
            .first()
        )

        if not waypoint_stoparea:
            self.request.response.status = 404
            return {'error': 'Waypoint Stoparea not found'}

        return {
            'waypoint_stoparea_id': waypoint_stoparea.waypoint_stoparea_id,
            'attributes': {
                'stoparea_id': waypoint_stoparea.stoparea_id,
                'waypoint_id': waypoint_stoparea.waypoint_id,
                'distance': waypoint_stoparea.distance,
            },
        }


def validate_waypoint_id(request, *args, **kwargs):
    """Check that the waypoint id is a number, as the other id validators."""
    try:
        request.matchdict['waypoint_id'] = int(request.matchdict['waypoint_id'])
    except KeyError, ValueError:
        request.errors.add('querystring', 'waypoint_id', 'invalid waypoint_id')


@resource(path='/waypoints/{waypoint_id}/stopareas')
class WaypointStopareasByWaypointRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Return the stopareas of a waypoint with their distance.

        Returns all stopareas associated with a waypoint,
        with their full attributes and distance.
        """
        waypoint_id = self.request.matchdict['waypoint_id']

        query = (
            DBSession.query(
                Stoparea,
                WaypointStoparea.distance,
                func.ST_X(Stoparea.geom).label('x'),
                func.ST_Y(Stoparea.geom).label('y'),
            )
            .join(
                WaypointStoparea, Stoparea.stoparea_id == WaypointStoparea.stoparea_id
            )
            .filter(WaypointStoparea.waypoint_id == waypoint_id)
            .all()
        )

        stopareas_data = [
            {**stoparea.to_dict(), 'distance': round(distance, 2)}
            for stoparea, distance, x, y in query
        ]

        return {'waypoint_id': waypoint_id, 'stopareas': stopareas_data}


@resource(path='/waypoints/{waypoint_id}/isReachable')
class WaypointStopareasReachableRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Return whether the waypoint has at least one stoparea.

        Returns true if the waypoint has at least one stoparea
        associated with it, false otherwise.
        """
        waypoint_id = self.request.matchdict['waypoint_id']

        has_stopareas = DBSession.query(
            exists().where(WaypointStoparea.waypoint_id == waypoint_id)
        ).scalar()

        return has_stopareas
