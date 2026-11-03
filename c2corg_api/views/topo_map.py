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
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import topo_map_documents_config
from c2corg_api.views.resource import view
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


@restricted_json_view(
    validators=[body_validator(TopoMapCreateSchema), validate_map_create],
    permission='moderator',
)
def create_topo_map(request):
    return create_document(request, topo_map_schema, after_add=insert_associations)


@restricted_json_view(
    validators=[
        body_validator(TopoMapUpdateSchema),
        validate_id,
        validate_map_update,
    ],
    permission='moderator',
)
def update_topo_map(request):
    return put_document(
        request, TopoMap, topo_map_schema, after_update=update_associations
    )


@view(validators=[validate_pagination, validate_preferred_lang_param])
def list_topo_maps(request):
    return collection_get(request, MAP_TYPE, topo_map_documents_config)


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_topo_map(request):
    return read_document(request, topo_map_documents_config, topo_map_schema)


@view(validators=[validate_id, validate_lang])
def get_topo_map_info(request):
    return document_info(request, topo_map_documents_config)


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
