import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from c2corg_api.views.document_schemas import waypoint_stop_documents_config
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, exists



from c2corg_api.models.waypoint_stop import (
    WaypointStop, schema_waypoint_stop, schema_update_waypoint_stop, WAYPOINT_STOP_TYPE, schema_create_waypoint_stop)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_api.models.stop import Stop

validate_waypoint_stop_create = make_validator_create(
    ['waypoint_id', 'stop_id', 'distance'], 'waypoint_id')
validate_waypoint_stop_update = make_validator_update(
    ['waypoint_id', 'stop_id', 'distance'], 'waypoint_id')

@resource(collection_path='/waypoints_stops', path='/waypoints_stops/{id}',
          cors_policy=cors_policy)
class WaypointStopRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of waypoint-stop associations.
        """
        return self._collection_get(WAYPOINT_STOP_TYPE, waypoint_stop_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single waypoint-stop association.
        """

        return self._get(waypoint_stop_documents_config, schema_waypoint_stop)

    @restricted_json_view(schema=schema_create_waypoint_stop,
                          validators=[
                              colander_body_validator,
                              validate_waypoint_stop_create])
    def collection_post(self):
        """
        Create a new waypoint-stop association.
        """
        return self._collection_post(schema_waypoint_stop)

    @restricted_json_view(schema=schema_update_waypoint_stop,
                          validators=[
                              colander_body_validator,
                              validate_id,
                              validate_waypoint_stop_update])
    def put(self):
        """
        Update a waypoint-stop association.
        """
        return self._put(WaypointStop, schema_waypoint_stop)

@resource(path='/waypoints_stops/{id}/{lang}/info', cors_policy=cors_policy)
class WaypointStopInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_waypoint_stop),

def validate_waypoint_id(request, *args, **kwargs):
    """Valide que waypoint_id est un entier valide."""
    try:
        request.matchdict['waypoint_id'] = int(request.matchdict['waypoint_id'])
    except (KeyError, ValueError):
        raise HTTPBadRequest(json_body={"error": "Invalid waypoint_id"})

@resource(path='/waypoints/{waypoint_id}/stops', cors_policy=cors_policy)
class WaypointStopsByWaypointRest:
    
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns all stops associated with a waypoint, with their full attributes and distance."""
        waypoint_id = self.request.matchdict['waypoint_id']

        query = (
            DBSession.query(
                Stop, 
                WaypointStop.distance,
                # Extraire X et Y directement sans transformation (en gardant SRID 3857)
                func.ST_X(DocumentGeometry.geom).label('x'),
                func.ST_Y(DocumentGeometry.geom).label('y')
            )
            .join(WaypointStop, Stop.document_id == WaypointStop.stop_id)
            .outerjoin(DocumentGeometry, DocumentGeometry.document_id == Stop.document_id)
            .filter(WaypointStop.waypoint_id == waypoint_id)
            .all()
        )

        stops_data = [
            {
                **stop.to_dict(),
                "distance": round(distance, 2),
                "coordinates": {
                    "x": x,
                    "y": y
                } if x is not None and y is not None else None
            }
            for stop, distance, x, y in query
        ]

        return {"waypoint_id": waypoint_id, "stops": stops_data}
    
@resource(path='/waypoints/{waypoint_id}/isReachable', cors_policy=cors_policy)
class WaypointStopsReachableRest:
    
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns true if the waypoint has at least one stop associated with it, false otherwise."""
        waypoint_id = self.request.matchdict['waypoint_id']

        has_stops = DBSession.query(
            exists().where(WaypointStop.waypoint_id == waypoint_id)
        ).scalar()

        return has_stops