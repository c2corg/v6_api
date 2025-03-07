import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from c2corg_api.views.document_schemas import waypoint_stoparea_documents_config
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, exists



from c2corg_api.models.waypoint_stoparea import (
    WaypointStoparea, schema_waypoint_stoparea, schema_update_waypoint_stoparea, WAYPOINT_STOPAREA_TYPE, schema_create_waypoint_stoparea)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param
from c2corg_api.models.stoparea import Stoparea

validate_waypoint_stoparea_create = make_validator_create(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id')
validate_waypoint_stoparea_update = make_validator_update(
    ['waypoint_id', 'stoparea_id', 'distance'], 'waypoint_id')

@resource(collection_path='/waypoints_stopareas', path='/waypoints_stopareas/{id}',
          cors_policy=cors_policy)
class WaypointStopareaRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of waypoint-stoparea associations.
        """
        return self._collection_get(WAYPOINT_STOPAREA_TYPE, waypoint_stoparea_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single waypoint-stoparea association.
        """

        return self._get(waypoint_stoparea_documents_config, schema_waypoint_stoparea)

    @restricted_json_view(schema=schema_create_waypoint_stoparea,
                          validators=[
                              colander_body_validator,
                              validate_waypoint_stoparea_create])
    def collection_post(self):
        """
        Create a new waypoint-stoparea association.
        """
        return self._collection_post(schema_waypoint_stoparea)

    @restricted_json_view(schema=schema_update_waypoint_stoparea,
                          validators=[
                              colander_body_validator,
                              validate_id,
                              validate_waypoint_stoparea_update])
    def put(self):
        """
        Update a waypoint-stoparea association.
        """
        return self._put(WaypointStoparea, schema_waypoint_stoparea)

@resource(path='/waypoints_stopareas/{id}/{lang}/info', cors_policy=cors_policy)
class WaypointStopareaInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_waypoint_stoparea),

def validate_waypoint_id(request, *args, **kwargs):
    """Valide que waypoint_id est un entier valide."""
    try:
        request.matchdict['waypoint_id'] = int(request.matchdict['waypoint_id'])
    except (KeyError, ValueError):
        raise HTTPBadRequest(json_body={"error": "Invalid waypoint_id"})

@resource(path='/waypoints/{waypoint_id}/stopareas', cors_policy=cors_policy)
class WaypointStopareasByWaypointRest:
    
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns all stopareas associated with a waypoint, with their full attributes and distance."""
        waypoint_id = self.request.matchdict['waypoint_id']

        query = (
            DBSession.query(
                Stoparea, 
                WaypointStoparea.distance,
                # Extraire X et Y directement sans transformation (en gardant SRID 3857)
                func.ST_X(DocumentGeometry.geom).label('x'),
                func.ST_Y(DocumentGeometry.geom).label('y')
            )
            .join(WaypointStoparea, Stoparea.document_id == WaypointStoparea.stoparea_id)
            .outerjoin(DocumentGeometry, DocumentGeometry.document_id == Stoparea.document_id)
            .filter(WaypointStoparea.waypoint_id == waypoint_id)
            .all()
        )

        stopareas_data = [
            {
                **stoparea.to_dict(),
                "distance": round(distance, 2),
                "coordinates": {
                    "x": x,
                    "y": y
                } if x is not None and y is not None else None
            }
            for stoparea, distance, x, y in query
        ]

        return {"waypoint_id": waypoint_id, "stopareas": stopareas_data}
    
@resource(path='/waypoints/{waypoint_id}/isReachable', cors_policy=cors_policy)
class WaypointStopareasReachableRest:
    
    def __init__(self, request):
        self.request = request

    @view(validators=[validate_waypoint_id])
    def get(self):
        """Returns true if the waypoint has at least one stoparea associated with it, false otherwise."""
        waypoint_id = self.request.matchdict['waypoint_id']

        has_stopareas = DBSession.query(
            exists().where(WaypointStoparea.waypoint_id == waypoint_id)
        ).scalar()

        return has_stopareas