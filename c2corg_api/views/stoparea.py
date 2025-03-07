import functools

from c2corg_api.models import DBSession
from c2corg_api.models.document import UpdateType
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from c2corg_api.views.document_schemas import stoparea_documents_config

from c2corg_api.models.stoparea import (
    Stoparea, schema_stoparea, schema_update_stoparea,
    STOPAREA_TYPE, schema_create_stoparea)

from c2corg_api.views.document import (
    DocumentRest, make_validator_create, make_validator_update)
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param

validate_stoparea_create = make_validator_create(
    ['navitia_id', 'stop_name', 'line', 'operator'], 'stop_name')
validate_stoparea_update = make_validator_update(
    ['navitia_id', 'stop_name', 'line', 'operator'], 'stop_name')

@resource(collection_path='/stopareas', path='/stopareas/{id}',
          cors_policy=cors_policy)
class StopareaRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        """
        Get a list of stopareas.
        """
        return self._collection_get(STOPAREA_TYPE, stoparea_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        """
        Get a single stoparea.
        """
        return self._get(stoparea_documents_config, schema_stoparea)

    @restricted_json_view(schema=schema_create_stoparea,
                          validators=[
                              colander_body_validator,
                              validate_stoparea_create])
    def collection_post(self):
        """
        Create a new stoparea.
        """
        return self._collection_post(schema_stoparea)

    @restricted_json_view(schema=schema_update_stoparea,
                          validators=[
                              colander_body_validator,
                              validate_id,
                              validate_stoparea_update])
    def put(self):
        """
        Update a stoparea.
        """
        return self._put(Stoparea, schema_stoparea)


@resource(path='/stopareas/{id}/{lang}/info', cors_policy=cors_policy)
class StopareaInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(schema_stoparea)
