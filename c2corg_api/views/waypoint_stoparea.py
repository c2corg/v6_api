from c2corg_api.models import DBSession
from c2corg_api.views.document_info import DocumentInfoRest
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, exists


from c2corg_api.models.waypoint_stoparea import (
    WaypointStoparea, schema_waypoint_stoparea)

from c2corg_api.views.document import (
    make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy
from c2corg_api.views.validation import validate_id, \
    validate_lang

from c2corg_api.models.stoparea import Stoparea

validate_waypoint_stoparea_create = make_validator_create(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id')
validate_waypoint_stoparea_update = make_validator_update(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id')


@resource(path='/waypoints_stopareas/{id}/{lang}/info',
          cors_policy=cors_policy)
class WaypointStopareaInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_waypoint_stoparea),


def validate_waypoint_id(request, *args, **kwargs):
    """Check if waypoint_stoparea_id is valid."""
    try:
        request.matchdict['waypoint_id'] = int(
            request.matchdict['waypoint_id'])
    except (KeyError, ValueError):
        raise HTTPBadRequest(json_body={"error": "Invalid waypoint_id"})


@resource(path='/waypoints/{waypoint_id}/stopareas', cors_policy=cors_policy)
class WaypointStopareasByWaypointRest:

    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns all stopareas associated with a waypoint, with their full attributes and distance."""  # noqa: E501
        waypoint_id = self.request.matchdict['waypoint_id']  # noqa: E501

        query = (
            DBSession.query(
                Stoparea,
                WaypointStoparea.distance,
                func.ST_X(Stoparea.geom).label('x'),
                func.ST_Y(Stoparea.geom).label('y')
            )
            .join(WaypointStoparea, Stoparea.stoparea_id == WaypointStoparea.stoparea_id)  # noqa: E501
            .filter(WaypointStoparea.waypoint_id == waypoint_id)
            .all()
        )

        stopareas_data = [
            {
                **stoparea.to_dict(),
                "distance": round(distance, 2)
            }
            for stoparea, distance, x, y in query
        ]

        return {"waypoint_id": waypoint_id, "stopareas": stopareas_data}


@resource(path='/waypoints/{waypoint_id}/isReachable', cors_policy=cors_policy)
class WaypointStopareasReachableRest:

    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns true if the waypoint has at least one stoparea associated with it, false otherwise."""  # noqa: E501
        waypoint_id = self.request.matchdict['waypoint_id']

        has_stopareas = DBSession.query(
            exists().where(WaypointStoparea.waypoint_id == waypoint_id)
        ).scalar()

        return has_stopareas
