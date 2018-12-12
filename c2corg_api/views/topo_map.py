from c2corg_api.models.cache_version import update_cache_version_for_map
from c2corg_api.models.document import UpdateType
from c2corg_api.models.topo_map import (
    TopoMap, schema_topo_map, schema_update_topo_map, MAP_TYPE)
from c2corg_api.models.topo_map_association import update_map
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import topo_map_documents_config
from c2corg_common.fields_topo_map import fields_topo_map
from cornice.resource import resource, view
from cornice.validators import colander_body_validator

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, validate_lang, \
    validate_cook_param

validate_map_create = make_validator_create(fields_topo_map.get('required'))
validate_map_update = make_validator_update(fields_topo_map.get('required'))


@resource(collection_path='/maps', path='/maps/{id}',
          cors_policy=cors_policy)
class TopoMapRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(MAP_TYPE, topo_map_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(TopoMap, schema_topo_map)

    @restricted_json_view(
        schema=schema_topo_map,
        validators=[colander_body_validator, validate_map_create],
        permission='moderator')
    def collection_post(self):
        return self._collection_post(
            schema_topo_map, after_add=insert_associations)

    @restricted_json_view(
        schema=schema_update_topo_map,
        validators=[colander_body_validator, validate_id, validate_map_update],
        permission='moderator')
    def put(self):
        return self._put(
            TopoMap, schema_topo_map, after_update=update_associations)


@resource(path='/maps/{id}/{lang}/info', cors_policy=cors_policy)
class TopoMapInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(TopoMap)


def insert_associations(topo_map, user_id):
    """Create links between this new map and documents.
    """
    update_map(topo_map, reset=False)


def update_associations(topo_map, update_types, user_id):
    """Update the links between this mapq and documents when the geometry
    has changed.
    """
    if update_types:
        # update cache key for currently associated docs
        update_cache_version_for_map(topo_map)

    if UpdateType.GEOM in update_types:
        update_map(topo_map, reset=True)
