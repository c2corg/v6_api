import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.models.waypoint_stop import (
    WaypointStop, schema_waypoint_stop, schema_update_waypoint_stop,
    ArchiveWaypointStop, WAYPOINT_STOP_TYPE, schema_create_waypoint_stop)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param

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
        return self._collection_get(WAYPOINT_STOP_TYPE)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single waypoint-stop association.
        """
        return self._get(schema_waypoint_stop)

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

@resource(path='/waypoints_stops/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class WaypointStopVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveWaypointStop, WAYPOINT_STOP_TYPE, schema_waypoint_stop)

@resource(path='/waypoints_stops/{id}/{lang}/info', cors_policy=cors_policy)
class WaypointStopInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_waypoint_stop)