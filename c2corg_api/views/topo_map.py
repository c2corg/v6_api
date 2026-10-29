from c2corg_api.models.cache_version import update_cache_version_for_map
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from c2corg_api.models.document import UpdateType
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap
from c2corg_api.models.topo_map_association import update_map
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.topo_map import (
    TopoMapCreateSchema,
    TopoMapUpdateSchema,
    topo_map_schema,
)
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document import (
    DocumentRest,
    make_validator_create,
    make_validator_update,
)
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import topo_map_documents_config
from c2corg_api.views.resource import resource, view
from c2corg_api.views.validation import (
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)

validate_map_create = make_validator_create(fields_topo_map.get('required'))
validate_map_update = make_validator_update(fields_topo_map.get('required'))


@resource(collection_path='/maps', path='/maps/{id}')
class TopoMapRest(DocumentRest):
    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(MAP_TYPE, topo_map_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(topo_map_documents_config, topo_map_schema)

    @restricted_json_view(
        validators=[body_validator(TopoMapCreateSchema), validate_map_create],
        permission='moderator',
    )
    def collection_post(self):
        return self._collection_post(topo_map_schema, after_add=insert_associations)

    @restricted_json_view(
        validators=[
            body_validator(TopoMapUpdateSchema),
            validate_id,
            validate_map_update,
        ],
        permission='moderator',
    )
    def put(self):
        return self._put(TopoMap, topo_map_schema, after_update=update_associations)


@resource(path='/maps/{id}/{lang}/info')
class TopoMapInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(topo_map_documents_config)


def insert_associations(topo_map, user_id):
    """Create links between this new map and documents."""
    update_map(topo_map, reset=False)


def update_associations(topo_map, update_types, user_id):
    """Update the links between this map and documents.

    Update the links between this map and documents when the geometry
    has changed.
    """
    if update_types:
        # update cache key for currently associated docs
        update_cache_version_for_map(topo_map)

    if UpdateType.GEOM in update_types:
        update_map(topo_map, reset=True)
