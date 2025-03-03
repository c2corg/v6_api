import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from c2corg_api.views.document_schemas import stop_documents_config

from c2corg_api.models.stop import (
    Stop, schema_stop, schema_update_stop,
    STOP_TYPE, schema_create_stop)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param

validate_stop_create = make_validator_create(
    ['navitia_id', 'stop_name', 'line', 'operator'], 'stop_name')
validate_stop_update = make_validator_update(
    ['navitia_id', 'stop_name', 'line', 'operator'], 'stop_name')

@resource(collection_path='/stops', path='/stops/{id}',
          cors_policy=cors_policy)
class StopRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of stops.
        """
        return self._collection_get(STOP_TYPE, stop_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single stop.
        """
        return self._get(stop_documents_config, schema_stop)

    @restricted_json_view(schema=schema_create_stop,
                          validators=[
                              colander_body_validator,
                              validate_stop_create])
    def collection_post(self):
        """
        Create a new stop.
        """
        return self._collection_post(schema_stop)

    @restricted_json_view(schema=schema_update_stop,
                          validators=[
                              colander_body_validator,
                              validate_id,
                              validate_stop_update])
    def put(self):
        """
        Update a stop.
        """
        return self._put(Stop, schema_stop)


@resource(path='/stops/{id}/{lang}/info', cors_policy=cors_policy)
class StopInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_stop)
