from c2corg_api.models.topo_map import (
    TopoMap, schema_topo_map, schema_update_topo_map)
from c2corg_common.fields_topo_map import fields_topo_map
from cornice.resource import resource, view

from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param


validate_map_create = make_validator_create(fields_topo_map.get('required'))
validate_map_update = make_validator_update(fields_topo_map.get('required'))


@resource(collection_path='/maps', path='/maps/{id}',
          cors_policy=cors_policy)
class TopoMapRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(TopoMap, schema_topo_map)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(TopoMap, schema_topo_map, include_maps=False)

    @restricted_json_view(
            schema=schema_topo_map, validators=validate_map_create,
            permission='moderator')
    def collection_post(self):
        return self._collection_post(TopoMap, schema_topo_map)

    @restricted_json_view(
            schema=schema_update_topo_map,
            validators=[validate_id, validate_map_update],
            permission='moderator')
    def put(self):
        return self._put(TopoMap, schema_topo_map)
